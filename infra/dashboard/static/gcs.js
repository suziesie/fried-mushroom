"use strict";

// D4D 관측소(GCS) 탭 — METT+TC mission_brief 빌더 + 온보드 파이프라인 실행기.
// GCS layer 01(src/gcs) 이 구현·배선됨(#111): 운용자는 set_mission(지시서 등)을
// 넘겨 실 layer 01 로 브리핑을 조립(assembleFromSetMission)하거나, 폼으로 직접
// 브리핑을 만들어 POST /gcs/run 할 수 있다. 판단은 온보드 파이프라인이 수행한다.
//
// 계약 (로그수집기 :8500 이 서빙 — collectorHttpUrl 기준):
//   GET  /gcs/scenarios       → [{tag, sortie_id, mission_context}]
//   GET  /gcs/scenario/{tag}  → {raw, mission_brief}
//   GET  /gcs/set-missions    → [{tag, sortie_id, mission_context}]   (layer 01 입력)
//   GET  /gcs/set-mission/{tag}→ set_mission 번들
//   POST /gcs/assemble        → {draft_brief, signal_cards, warnings, correlation_id}
//   POST /gcs/run             → {result, log_published, correlation_id}
// 폼 ↔ JSON 라운드트립: 편집 → collectBrief() → 미리보기 = 전송 body.
// assemble→run 시 correlation_id 를 이어주면 조립·사이클 로그가 대시보드에서 연결된다.

(function () {
  const $ = (id) => document.getElementById(id);

  // 바인딩 상태 — raw 센서 입력 + 기지 id(브리핑 로드 시 원본 id 보존).
  const gcs = {
    raw: null,
    rawTag: null,
    baseIds: { emergency: "base_emergency", alternate: "base_alternate" },
    // #111: /gcs/assemble(실 layer 01)이 발급한 상관ID. run 에 이어주면
    // 조립·사이클 로그가 스트림에서 연결된다. 수동 프리셋 로드 시 해제.
    correlationId: null,
  };

  // ── 수집기 API 헬퍼 ─────────────────────────────────────────
  // /gcs/* 는 로그수집기(:8500)가 서빙 — app.js 의 공유 설정 로더(window.D4D_CONFIG)
  // 에서 collectorHttpUrl 을 해석해 브라우저가 수집기에 직접 요청한다(정적 배포 대응).

  const DEFAULT_COLLECTOR_HTTP_URL = "http://localhost:8500";

  function configReady() {
    return typeof window !== "undefined" && window.D4D_CONFIG
      ? window.D4D_CONFIG
      : Promise.resolve(null);
  }

  /** collectorHttpUrl + path 로 fetch — 설정 해석을 기다린 뒤 요청한다. */
  function collectorFetch(path, opts) {
    return configReady()
      .then((cfg) => (cfg && cfg.collectorHttpUrl) || DEFAULT_COLLECTOR_HTTP_URL)
      .then((base) => fetch(base + path, opts));
  }

  /**
   * #111: set_mission 태그 → 실 layer 01 조립.
   * GET /gcs/set-mission/{tag} → POST /gcs/assemble.
   * 반환 {draft_brief, signal_cards, warnings, correlation_id}.
   * draft_brief 는 6-필드 mission_brief 이므로 그대로 /gcs/run 에 투입 가능
   * (correlation_id 를 함께 넘기면 조립·사이클 로그가 연결됨).
   */
  function assembleFromSetMission(tag) {
    return collectorFetch("/gcs/set-mission/" + encodeURIComponent(tag))
      .then((r) => {
        if (!r.ok) throw new Error("set_mission 로드 실패: " + tag);
        return r.json();
      })
      .then((setMission) =>
        collectorFetch("/gcs/assemble", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ set_mission: setMission }),
        }),
      )
      .then((r) => {
        if (!r.ok) throw new Error("assemble 실패");
        return r.json();
      });
  }
  // 외부(향후 리뷰 패널 UI)에서 참조 가능하도록 노출.
  if (typeof window !== "undefined") window.assembleFromSetMission = assembleFromSetMission;

  const DEFAULT_BRIEF = {
    sortie_id: "",
    mission_context: "정찰",
    posture: { watchcon: 4, defcon: 4, infocon: 5 },
    drone_profile: { armament: [], spare_asset_available: false, battery_pct: 100 },
    corridor: {
      waypoints: [{ id: "wp1", lat: 37.5, lon: 127.0, alt_m: 120 }],
      bases: {
        emergency: { id: "base_emergency", lat: 37.49, lon: 127.0, alt_m: 50 },
        alternate: { id: "base_alternate", lat: 37.48, lon: 127.005, alt_m: 50 },
      },
    },
    weights: { stealth: 0.4, survival: 0.35, info_value: 0.2, timeliness: 0.05 },
  };

  // ── 폼 유틸 ─────────────────────────────────────────────────

  function numVal(input, fallback) {
    const v = Number(input && input.value);
    return Number.isFinite(v) && input.value !== "" ? v : fallback;
  }

  function setNum(id, value, fallback) {
    const v = Number(value);
    $(id).value = Number.isFinite(v) ? v : fallback;
  }

  /** select 값 설정 — 목록에 없는 값이면 옵션을 추가해 손실 없이 라운드트립. */
  function setSelect(sel, value, fallback) {
    const want = value != null ? String(value) : fallback;
    sel.value = want;
    if (sel.value !== want) {
      const opt = document.createElement("option");
      opt.value = want;
      opt.textContent = want;
      sel.appendChild(opt);
      sel.value = want;
    }
  }

  function setStatus(msg, cls) {
    const node = $("gcs-run-status");
    if (!node) return;
    node.textContent = msg;
    node.className = "gcs-status" + (cls ? " " + cls : "");
    node.title = msg;
  }

  // ── 웨이포인트 테이블 ───────────────────────────────────────

  function addWpRow(wp) {
    const tbody = $("gcs-wp-body");
    const tr = document.createElement("tr");

    const mkCell = (cls, type, value) => {
      const td = document.createElement("td");
      const input = document.createElement("input");
      input.type = type;
      input.className = cls;
      if (type === "number") input.step = "any";
      input.value = value;
      td.appendChild(input);
      tr.appendChild(td);
    };

    mkCell("wp-id", "text", wp && wp.id != null ? wp.id : "wp" + (tbody.childElementCount + 1));
    mkCell("wp-lat", "number", wp && wp.lat != null ? wp.lat : 37.5);
    mkCell("wp-lon", "number", wp && wp.lon != null ? wp.lon : 127.0);
    mkCell("wp-alt", "number", wp && wp.alt_m != null ? wp.alt_m : 120);

    const td = document.createElement("td");
    const rm = document.createElement("button");
    rm.type = "button";
    rm.className = "gcs-btn gcs-wp-remove";
    rm.textContent = "−";
    rm.title = "행 삭제";
    rm.addEventListener("click", () => {
      tr.remove();
      updatePreview();
    });
    td.appendChild(rm);
    tr.appendChild(td);

    tbody.appendChild(tr);
  }

  // ── 폼 → mission_brief 조립 / mission_brief → 폼 채우기 ─────

  function collectBrief() {
    const waypoints = Array.from(document.querySelectorAll("#gcs-wp-body tr")).map((tr, i) => ({
      id: tr.querySelector(".wp-id").value.trim() || "wp" + (i + 1),
      lat: numVal(tr.querySelector(".wp-lat"), 0),
      lon: numVal(tr.querySelector(".wp-lon"), 0),
      alt_m: numVal(tr.querySelector(".wp-alt"), 0),
    }));
    const armament = $("gcs-armament").value
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    return {
      sortie_id: $("gcs-sortie-id").value.trim(),
      mission_context: $("gcs-mission-context").value,
      posture: {
        watchcon: numVal($("gcs-watchcon"), 4),
        defcon: numVal($("gcs-defcon"), 4),
        infocon: numVal($("gcs-infocon"), 5),
      },
      drone_profile: {
        armament,
        spare_asset_available: $("gcs-spare-asset").checked,
        battery_pct: numVal($("gcs-battery-pct"), 100),
      },
      corridor: {
        waypoints,
        bases: {
          emergency: {
            id: gcs.baseIds.emergency,
            lat: numVal($("gcs-base-em-lat"), 0),
            lon: numVal($("gcs-base-em-lon"), 0),
            alt_m: numVal($("gcs-base-em-alt"), 0),
          },
          alternate: {
            id: gcs.baseIds.alternate,
            lat: numVal($("gcs-base-al-lat"), 0),
            lon: numVal($("gcs-base-al-lon"), 0),
            alt_m: numVal($("gcs-base-al-alt"), 0),
          },
        },
      },
      weights: {
        stealth: numVal($("gcs-w-stealth"), 0),
        survival: numVal($("gcs-w-survival"), 0),
        info_value: numVal($("gcs-w-info"), 0),
        timeliness: numVal($("gcs-w-time"), 0),
      },
    };
  }

  function fillBase(prefix, base, fallback, key) {
    const b = base || fallback;
    gcs.baseIds[key] = b.id != null ? b.id : fallback.id;
    setNum("gcs-base-" + prefix + "-lat", b.lat, fallback.lat);
    setNum("gcs-base-" + prefix + "-lon", b.lon, fallback.lon);
    setNum("gcs-base-" + prefix + "-alt", b.alt_m, fallback.alt_m);
  }

  function fillForm(brief) {
    const b = brief || {};
    const posture = b.posture || {};
    const dp = b.drone_profile || {};
    const corridor = b.corridor || {};
    const bases = corridor.bases || {};
    const weights = b.weights || {};
    const D = DEFAULT_BRIEF;

    $("gcs-sortie-id").value = b.sortie_id || "";
    setSelect($("gcs-mission-context"), b.mission_context, D.mission_context);
    setNum("gcs-watchcon", posture.watchcon, D.posture.watchcon);
    setNum("gcs-defcon", posture.defcon, D.posture.defcon);
    setNum("gcs-infocon", posture.infocon, D.posture.infocon);
    setNum("gcs-battery-pct", dp.battery_pct, D.drone_profile.battery_pct);
    $("gcs-spare-asset").checked = !!dp.spare_asset_available;
    $("gcs-armament").value = Array.isArray(dp.armament) ? dp.armament.join(", ") : "";

    $("gcs-wp-body").textContent = "";
    const wps = Array.isArray(corridor.waypoints) && corridor.waypoints.length
      ? corridor.waypoints
      : D.corridor.waypoints;
    wps.forEach(addWpRow);
    fillBase("em", bases.emergency, D.corridor.bases.emergency, "emergency");
    fillBase("al", bases.alternate, D.corridor.bases.alternate, "alternate");

    setNum("gcs-w-stealth", weights.stealth, D.weights.stealth);
    setNum("gcs-w-survival", weights.survival, D.weights.survival);
    setNum("gcs-w-info", weights.info_value, D.weights.info_value);
    setNum("gcs-w-time", weights.timeliness, D.weights.timeliness);
  }

  function updatePreview() {
    $("gcs-json-preview").textContent = JSON.stringify(collectBrief(), null, 2);
  }

  // ── 시나리오 프리셋 / raw 바인딩 ─────────────────────────────

  function markActivePreset(tag) {
    document.querySelectorAll(".gcs-preset").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.tag === tag);
    });
  }

  function bindRaw(tag, raw) {
    gcs.raw = raw;
    gcs.rawTag = tag;
    const seq = raw && raw.seq != null ? " (seq=" + raw.seq + ")" : "";
    $("gcs-raw-bound").textContent = "raw: raw_" + tag + ".json" + seq;
    const sel = $("gcs-raw-select");
    if (sel && sel.value !== tag) sel.value = tag;
  }

  function fetchScenario(tag) {
    return collectorFetch("/gcs/scenario/" + encodeURIComponent(tag)).then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  }

  /** 프리셋 선택 — 브리핑 폼 채우기 + raw 바인딩. (수동 브리핑 → 01 조립 상관ID 해제) */
  function loadScenario(tag) {
    return fetchScenario(tag)
      .then((data) => {
        fillForm(data.mission_brief || {});
        bindRaw(tag, data.raw || null);
        gcs.correlationId = null;
        markActivePreset(tag);
        updatePreview();
        setStatus("프리셋 " + tag + " 로드 완료", "");
      })
      .catch((e) => setStatus("프리셋 로드 실패(" + tag + "): " + e.message, "err"));
  }

  /** #111: 지시서(set_mission) 프리셋 → 실 layer 01 조립 → 폼 채움 + 상관ID 보관. */
  function loadFromLayer01(tag) {
    setStatus("layer 01 조립 중… (" + tag + ")", "");
    return assembleFromSetMission(tag)
      .then((body) => {
        fillForm(body.draft_brief || {});
        gcs.correlationId = body.correlation_id || null;
        markActivePreset("01:" + tag);
        updatePreview();
        const cards = (body.signal_cards || []).map((c) => c.source_phrase).join(", ");
        const nWarn = (body.warnings || []).length;
        let msg = "01 조립 완료 · 신호카드 [" + (cards || "없음") + "] · 경고 " + nWarn;
        if (!gcs.raw) msg += " — raw 미선택: raw 선택기에서 지정 후 실행";
        setStatus(msg, nWarn ? "err" : "ok");
      })
      .catch((e) => setStatus("layer 01 조립 실패(" + tag + "): " + e.message, "err"));
  }

  /** #111: set_mission 프리셋 목록을 시나리오 패널에 렌더 (실 layer 01 경로). */
  function loadSetMissions() {
    return collectorFetch("/gcs/set-missions")
      .then((r) => {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then((items) => {
        if (!items || !items.length) return;
        const list = $("gcs-scenario-list");
        const head = document.createElement("div");
        head.className = "gcs-preset-head";
        head.textContent = "지시서 → layer 01 조립";
        list.appendChild(head);
        items.forEach((it) => {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "gcs-preset gcs-preset-01";
          btn.dataset.tag = "01:" + it.tag;
          const tagEl = document.createElement("span");
          tagEl.className = "gcs-preset-tag";
          tagEl.textContent = "01·" + String(it.tag).toUpperCase();
          const meta = document.createElement("span");
          meta.className = "gcs-preset-meta";
          meta.textContent = (it.sortie_id || "—") + " · " + (it.mission_context || "—");
          btn.append(tagEl, meta);
          btn.addEventListener("click", () => loadFromLayer01(it.tag));
          list.appendChild(btn);
        });
      })
      .catch((e) => setStatus("set_mission 목록 조회 실패: " + e.message, "err"));
  }

  /** raw 선택기 변경 — raw 만 교체(브리핑 폼은 유지). */
  function loadRawOnly(tag) {
    return fetchScenario(tag)
      .then((data) => {
        bindRaw(tag, data.raw || null);
        setStatus("raw 센서 입력 → raw_" + tag + ".json", "");
      })
      .catch((e) => setStatus("raw 로드 실패(" + tag + "): " + e.message, "err"));
  }

  function loadScenarios() {
    return collectorFetch("/gcs/scenarios")
      .then((r) => {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then((items) => {
        const list = $("gcs-scenario-list");
        const sel = $("gcs-raw-select");
        list.textContent = "";
        sel.textContent = "";
        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = "— 선택 —";
        sel.appendChild(placeholder);
        (items || []).forEach((it) => {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "gcs-preset";
          btn.dataset.tag = it.tag;
          const tagEl = document.createElement("span");
          tagEl.className = "gcs-preset-tag";
          tagEl.textContent = String(it.tag).toUpperCase();
          const meta = document.createElement("span");
          meta.className = "gcs-preset-meta";
          meta.textContent = (it.sortie_id || "—") + " · " + (it.mission_context || "—");
          btn.append(tagEl, meta);
          btn.addEventListener("click", () => loadScenario(it.tag));
          list.appendChild(btn);

          const opt = document.createElement("option");
          opt.value = it.tag;
          opt.textContent = "raw_" + it.tag + ".json";
          sel.appendChild(opt);
        });
      })
      .catch((e) => setStatus("시나리오 목록 조회 실패: " + e.message, "err"));
  }

  // ── 검증 / 실행 ─────────────────────────────────────────────

  function validateBrief(brief) {
    const errs = [];
    if (!brief.sortie_id) errs.push("sortie_id 필수");
    ["watchcon", "defcon", "infocon"].forEach((k) => {
      const v = brief.posture[k];
      if (!(v >= 1 && v <= 5)) errs.push(k + " 1..5");
    });
    const bp = brief.drone_profile.battery_pct;
    if (!(bp >= 0 && bp <= 100)) errs.push("battery_pct 0..100");
    if (brief.corridor.waypoints.length < 1) errs.push("waypoint 1개 이상 필요");
    Object.keys(brief.weights).forEach((k) => {
      const v = brief.weights[k];
      if (!(v >= 0 && v <= 1)) errs.push("weights." + k + " 0..1");
    });
    if (!gcs.raw) errs.push("raw 센서 입력 미바인딩(프리셋 또는 raw 선택)");
    return errs;
  }

  /** 임무 전달 — POST /gcs/run 후 요약 표시, 성공 시 관측 탭으로 자동 전환. */
  function runPipeline() {
    const brief = collectBrief();
    const errs = validateBrief(brief);
    if (errs.length) {
      setStatus("검증 실패: " + errs.join(" · "), "err");
      return;
    }
    setStatus("파이프라인 실행 중…", "");
    $("gcs-run").disabled = true;
    collectorFetch("/gcs/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        raw: gcs.raw,
        mission_brief: brief,
        // 01 조립을 거친 브리핑이면 상관ID 를 이어 조립·사이클 로그를 연결(#111).
        ...(gcs.correlationId ? { correlation_id: gcs.correlationId } : {}),
      }),
    })
      .then((r) => r.json().then((data) => ({ ok: r.ok, data })))
      .then(({ ok, data }) => {
        if (!ok) throw new Error(data && data.detail ? String(data.detail) : "실행 실패");
        const res = data.result || {};
        const primary = res.threat && res.threat.primary
          ? res.threat.primary.threat_event
          : "없음";
        const cands = (res.risk && res.risk.candidates) || [];
        let rac = (res.risk && res.risk.ambient_rac) || "—";
        if (cands.length) {
          const top = cands.reduce((a, b) => {
            const ra = a && a.priority_rank != null ? a.priority_rank : Infinity;
            const rb = b && b.priority_rank != null ? b.priority_rank : Infinity;
            return ra <= rb ? a : b;
          });
          if (top && top.rac != null) rac = top.rac;
        }
        const action = (res.flight_plan && res.flight_plan.flight_action) ||
          (res.response && res.response.flight_action) || "—";
        setStatus(
          "[" + data.correlation_id + "] primary=" + primary + " · RAC=" + rac +
            " · flight_action=" + action +
            (data.log_published ? " · 로그 발행됨 → 관측 탭" : " · 로그 미발행(수집기 확인)"),
          "ok"
        );
        // 요약 확인 여유 후 관측 탭으로 전환(시스템 로그에 사이클 로그가 흐른다).
        setTimeout(() => {
          if (typeof switchTab === "function") switchTab("observation");
        }, 1200);
      })
      .catch((e) => setStatus("실행 실패: " + e.message, "err"))
      .finally(() => {
        $("gcs-run").disabled = false;
      });
  }

  // ── 진입점 ──────────────────────────────────────────────────

  function init() {
    if (!$("gcs-form")) return;
    fillForm(DEFAULT_BRIEF);
    updatePreview();

    $("gcs-form").addEventListener("input", updatePreview);
    $("gcs-form").addEventListener("change", updatePreview);
    $("gcs-form").addEventListener("submit", (e) => e.preventDefault());
    $("gcs-wp-add").addEventListener("click", () => {
      addWpRow(null);
      updatePreview();
    });
    $("gcs-reset").addEventListener("click", () => {
      fillForm(DEFAULT_BRIEF);
      markActivePreset(null);
      updatePreview();
      setStatus("초기화됨", "");
    });
    $("gcs-validate").addEventListener("click", () => {
      const errs = validateBrief(collectBrief());
      setStatus(errs.length ? "검증 실패: " + errs.join(" · ") : "검증 통과", errs.length ? "err" : "ok");
    });
    $("gcs-run").addEventListener("click", runPipeline);
    $("gcs-raw-select").addEventListener("change", (e) => {
      if (e.target.value) loadRawOnly(e.target.value);
    });

    loadScenarios().then(loadSetMissions);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
