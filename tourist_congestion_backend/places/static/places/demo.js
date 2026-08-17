(() => {
  "use strict";

  const API = {
    places: "/api/places",
    nearby: "/api/places/nearby",
    health: "/healthz",
  };

  const PALACE_CENTER = {
    latitude: 37.576031,
    longitude: 126.976722,
    radiusKm: 3,
  };

  const CROWD_LABELS = {
    relaxed: "여유",
    normal: "보통",
    busy: "약간 붐빔",
    crowded: "붐빔",
    unknown: "정보 확인 중",
  };

  const REGION_LABELS = {
    11: "서울",
    12: "광주",
    26: "부산",
    27: "대구",
    28: "인천",
    29: "광주",
    30: "대전",
    31: "울산",
    36: "세종",
    41: "경기",
    42: "강원",
    43: "충북",
    44: "충남",
    45: "전북",
    46: "전남",
    47: "경북",
    48: "경남",
    50: "제주",
    51: "강원",
    52: "전북",
  };

  const elements = {
    form: document.querySelector("#place-search"),
    keyword: document.querySelector("#keyword"),
    region: document.querySelector("#region-code"),
    category: document.querySelector("#category"),
    crowdLevel: document.querySelector("#crowd-level"),
    results: document.querySelector("#place-results"),
    loading: document.querySelector("#loading-state"),
    error: document.querySelector("#error-state"),
    errorMessage: document.querySelector("#error-message"),
    empty: document.querySelector("#empty-state"),
    context: document.querySelector("#result-context"),
    retry: document.querySelector("#retry-load"),
    refresh: document.querySelector("#refresh-results"),
    useLocation: document.querySelector("#use-location"),
    chips: [...document.querySelectorAll(".filter-chip")],
    statTotal: document.querySelector("#stat-total"),
    statCrowd: document.querySelector("#stat-crowd"),
    statRegions: document.querySelector("#stat-regions"),
    statUpdated: document.querySelector("#stat-updated"),
    health: document.querySelector("#api-health"),
    healthText: document.querySelector("#api-health-text"),
    dialog: document.querySelector("#detail-dialog"),
    detailContent: document.querySelector("#detail-content"),
    closeDetail: document.querySelector("#close-detail"),
  };

  const state = {
    lastRequest: null,
    listController: null,
    detailController: null,
  };

  function createElement(tag, options = {}) {
    const element = document.createElement(tag);
    if (options.className) element.className = options.className;
    if (options.text !== undefined) element.textContent = String(options.text);
    if (options.attributes) {
      Object.entries(options.attributes).forEach(([name, value]) => {
        if (value !== null && value !== undefined) {
          element.setAttribute(name, String(value));
        }
      });
    }
    return element;
  }

  function setVisible(element, visible) {
    element.classList.toggle("hidden", !visible);
  }

  function setScreen(name) {
    setVisible(elements.loading, name === "loading");
    setVisible(elements.error, name === "error");
    setVisible(elements.empty, name === "empty");
    setVisible(elements.results, name === "results");
    elements.results.setAttribute("aria-busy", name === "loading" ? "true" : "false");
  }

  function crowdPresentation(crowd) {
    if (!crowd) return { level: "unavailable", label: "혼잡도 미제공" };
    const level = CROWD_LABELS[crowd.level] ? crowd.level : "unknown";
    return { level, label: CROWD_LABELS[level] };
  }

  function regionLabel(place) {
    const code = String(place.region_code || "").slice(0, 2);
    if (REGION_LABELS[code]) return REGION_LABELS[code];
    const firstAddressPart = String(place.address || "").trim().split(/\s+/)[0];
    return firstAddressPart || "지역 미상";
  }

  function formatDate(value, options = {}) {
    if (!value) return "관측 시각 없음";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "관측 시각 없음";
    return new Intl.DateTimeFormat("ko-KR", {
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      ...options,
    }).format(date);
  }

  function formatPopulation(crowd) {
    if (!crowd || crowd.population_min == null || crowd.population_max == null) {
      return "인구 범위 미제공";
    }
    const formatter = new Intl.NumberFormat("ko-KR");
    return `${formatter.format(crowd.population_min)}~${formatter.format(crowd.population_max)}명`;
  }

  function addImage(container, source, alt, className = "place-image") {
    const fallback = createElement("span", {
      className: "image-fallback",
      text: "⌖",
      attributes: { "aria-hidden": "true" },
    });
    container.append(fallback);
    if (!source) return;

    const image = createElement("img", {
      className,
      attributes: {
        src: source,
        alt,
        loading: "lazy",
        referrerpolicy: "no-referrer",
      },
    });
    image.addEventListener("load", () => fallback.remove(), { once: true });
    image.addEventListener("error", () => image.remove(), { once: true });
    container.append(image);
  }

  function makeCrowdBadge(crowd) {
    const presentation = crowdPresentation(crowd);
    return createElement("span", {
      className: `crowd-badge ${presentation.level}`,
      text: presentation.label,
    });
  }

  function buildPlaceCard(place) {
    const card = createElement("button", {
      className: "place-card",
      attributes: {
        type: "button",
        "data-place-id": place.id,
        "aria-label": `${place.name} 상세 보기`,
      },
    });

    const imageWrap = createElement("span", { className: "place-image-wrap" });
    addImage(imageWrap, place.image_url, `${place.name} 대표 이미지`);
    if (typeof place.distance_km === "number") {
      imageWrap.append(
        createElement("span", {
          className: "distance-pill",
          text: place.distance_km < 1
            ? `${Math.round(place.distance_km * 1000)}m`
            : `${place.distance_km.toFixed(1)}km`,
        }),
      );
    }

    const body = createElement("span", { className: "place-card-body" });
    const topLine = createElement("span", { className: "card-topline" });
    topLine.append(
      createElement("span", { className: "category-label", text: place.category || "장소" }),
      createElement("span", { className: "region-label", text: regionLabel(place) }),
    );
    body.append(topLine);
    body.append(createElement("h3", { text: place.name }));
    body.append(
      createElement("span", {
        className: "place-address",
        text: place.address || "주소 정보가 아직 없습니다.",
      }),
    );

    const footer = createElement("span", { className: "card-footer" });
    footer.append(makeCrowdBadge(place.latest_crowd));
    footer.append(
      createElement("span", {
        className: "observed-time",
        text: place.latest_crowd
          ? `${formatDate(place.latest_crowd.observed_at)} 기준`
          : "전국 장소 데이터",
      }),
    );
    body.append(footer);
    card.append(imageWrap, body);
    card.addEventListener("click", () => openPlaceDetail(place.id));
    return card;
  }

  function updateStats(items) {
    const regions = new Set(items.map(regionLabel).filter(Boolean));
    const crowdCount = items.filter((place) => place.latest_crowd).length;
    elements.statTotal.textContent = `${items.length}곳`;
    elements.statCrowd.textContent = `${crowdCount}곳`;
    elements.statRegions.textContent = `${regions.size}개`;
    elements.statUpdated.textContent = new Intl.DateTimeFormat("ko-KR", {
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date());
  }

  function renderPlaces(items, context) {
    elements.results.replaceChildren(...items.map(buildPlaceCard));
    updateStats(items);
    elements.context.textContent = `${context} · ${items.length}곳`;
    setScreen(items.length ? "results" : "empty");
  }

  function setActiveChip(action) {
    elements.chips.forEach((chip) => {
      chip.classList.toggle("active", chip.dataset.action === action);
    });
  }

  function resetFields() {
    elements.form.reset();
  }

  function makeListRequest({ context = "검색 결과", onlyWithCrowd = false } = {}) {
    const params = new URLSearchParams({ page_size: "100" });
    const values = {
      keyword: elements.keyword.value.trim(),
      region_code: elements.region.value,
      category: elements.category.value,
      crowd_level: elements.crowdLevel.value,
    };
    Object.entries(values).forEach(([key, value]) => {
      if (value) params.set(key, value);
    });
    return {
      url: `${API.places}?${params}`,
      context,
      onlyWithCrowd,
    };
  }

  function makeNearbyRequest(latitude, longitude, radiusKm, context) {
    const params = new URLSearchParams({
      latitude: String(latitude),
      longitude: String(longitude),
      radius_km: String(radiusKm),
      page_size: "100",
    });
    if (elements.category.value) params.set("category", elements.category.value);
    if (elements.crowdLevel.value) params.set("crowd_level", elements.crowdLevel.value);
    return { url: `${API.nearby}?${params}`, context, onlyWithCrowd: false };
  }

  async function fetchJson(url, signal) {
    const response = await fetch(url, {
      headers: { Accept: "application/json" },
      signal,
    });
    let payload;
    try {
      payload = await response.json();
    } catch (_error) {
      throw new Error(`API가 JSON이 아닌 응답을 반환했습니다. (HTTP ${response.status})`);
    }
    if (!response.ok || !payload.success) {
      throw new Error(payload.message || `API 요청에 실패했습니다. (HTTP ${response.status})`);
    }
    return payload.data;
  }

  async function loadPlaces(request, { remember = true } = {}) {
    if (remember) state.lastRequest = request;
    if (state.listController) state.listController.abort();
    state.listController = new AbortController();
    setScreen("loading");
    elements.context.textContent = `${request.context}을 불러오고 있습니다.`;

    try {
      const data = await fetchJson(request.url, state.listController.signal);
      let items = Array.isArray(data.items) ? data.items : [];
      if (request.onlyWithCrowd) {
        items = items.filter((place) => place.latest_crowd);
      }
      renderPlaces(items, request.context);
      setHealth(true);
    } catch (error) {
      if (error.name === "AbortError") return;
      elements.errorMessage.textContent = error.message;
      elements.context.textContent = "장소 API 연결을 확인해주세요.";
      setScreen("error");
      setHealth(false);
    }
  }

  function setHealth(connected) {
    elements.health.classList.toggle("connected", connected);
    elements.health.classList.toggle("failed", !connected);
    elements.healthText.textContent = connected ? "API 연결됨" : "API 연결 실패";
  }

  async function checkHealth() {
    try {
      const response = await fetch(API.health, { headers: { Accept: "application/json" } });
      setHealth(response.ok);
    } catch (_error) {
      setHealth(false);
    }
  }

  function addFact(list, label, value, link = null) {
    if (!value) return;
    const wrapper = createElement("div", { className: "fact" });
    wrapper.append(createElement("dt", { text: label }));
    const detail = createElement("dd");
    if (link) {
      detail.append(
        createElement("a", {
          text: value,
          attributes: { href: link, target: "_blank", rel: "noopener noreferrer" },
        }),
      );
    } else {
      detail.textContent = value;
    }
    wrapper.append(detail);
    list.append(wrapper);
  }

  function safeWebUrl(value) {
    if (!value) return null;
    try {
      const url = new URL(value);
      return ["http:", "https:"].includes(url.protocol) ? url.href : null;
    } catch (_error) {
      return null;
    }
  }

  function buildDetail(place) {
    const fragment = document.createDocumentFragment();
    const hero = createElement("div", { className: "detail-hero" });
    addImage(hero, place.image_url || place.info?.first_image_url, `${place.name} 대표 이미지`, "");
    fragment.append(hero);

    const body = createElement("div", { className: "detail-body" });
    body.append(
      createElement("div", {
        className: "detail-overline",
        text: `${place.category || "장소"} · ${regionLabel(place)}`,
      }),
    );
    body.append(createElement("h2", { text: place.name, attributes: { id: "detail-title" } }));
    body.append(
      createElement("p", {
        className: "detail-address",
        text: place.address || "주소 정보가 아직 없습니다.",
      }),
    );

    const crowd = createElement("div", { className: "detail-crowd" });
    crowd.append(createElement("span", { className: "detail-crowd-icon", text: "⌁" }));
    const crowdCopy = createElement("span");
    crowdCopy.append(
      createElement("strong", {
        text: place.latest_crowd
          ? `${place.latest_crowd.area_name || "주변"} 최신 혼잡도`
          : "혼잡도 연결 준비 중",
      }),
      createElement("small", {
        text: place.latest_crowd
          ? `${formatPopulation(place.latest_crowd)} · ${formatDate(place.latest_crowd.observed_at)} 기준`
          : "현재 서울 일부 장소에서만 제공됩니다.",
      }),
    );
    crowd.append(crowdCopy, makeCrowdBadge(place.latest_crowd));
    body.append(crowd);

    const info = place.info;
    if (info?.description) {
      const section = createElement("section", { className: "detail-section" });
      section.append(createElement("h3", { text: "장소 소개" }));
      section.append(createElement("p", { className: "detail-description", text: info.description }));
      body.append(section);
    }

    const facts = createElement("dl", { className: "detail-facts" });
    addFact(facts, "전화", info?.phone);
    addFact(facts, "운영 시간", info?.opening_hours);
    addFact(facts, "휴무일", info?.holiday_info);
    addFact(facts, "공간 유형", place.indoor_outdoor && place.indoor_outdoor !== "unknown" ? place.indoor_outdoor : "정보 없음");
    const homepage = safeWebUrl(info?.homepage_url);
    if (homepage) addFact(facts, "홈페이지", "공식 페이지 열기 ↗", homepage);
    addFact(facts, "상세정보 출처", info?.source);
    if (facts.childElementCount) body.append(facts);

    if (Array.isArray(info?.tags) && info.tags.length) {
      const tags = createElement("div", { className: "detail-tags", attributes: { "aria-label": "장소 태그" } });
      info.tags.forEach((tag) => {
        if (tag) tags.append(createElement("span", { className: "detail-tag", text: `# ${tag}` }));
      });
      if (tags.childElementCount) body.append(tags);
    }

    if (!info) {
      const section = createElement("section", { className: "detail-section" });
      section.append(createElement("h3", { text: "장소 상세정보" }));
      section.append(
        createElement("p", {
          className: "detail-description",
          text: "이 장소의 TourAPI 상세정보는 아직 보강 전입니다. 기본 장소 정보는 정상적으로 연결되어 있습니다.",
        }),
      );
      body.append(section);
    }

    fragment.append(body);
    return fragment;
  }

  async function openPlaceDetail(placeId) {
    if (state.detailController) state.detailController.abort();
    state.detailController = new AbortController();
    elements.detailContent.replaceChildren();
    const loading = createElement("div", { className: "feedback detail-loading" });
    loading.append(
      createElement("span", { className: "spinner", attributes: { "aria-hidden": "true" } }),
      createElement("strong", { text: "장소 상세정보를 불러오는 중입니다" }),
    );
    elements.detailContent.append(loading);
    if (!elements.dialog.open) elements.dialog.showModal();

    try {
      const place = await fetchJson(`${API.places}/${encodeURIComponent(placeId)}`, state.detailController.signal);
      elements.detailContent.replaceChildren(buildDetail(place));
    } catch (error) {
      if (error.name === "AbortError") return;
      const errorBox = createElement("div", { className: "feedback detail-loading error-state" });
      errorBox.append(
        createElement("span", { text: "!", attributes: { "aria-hidden": "true" } }),
        createElement("strong", { text: "상세정보를 불러오지 못했습니다" }),
        createElement("small", { text: error.message }),
      );
      elements.detailContent.replaceChildren(errorBox);
    }
  }

  function useCurrentLocation() {
    if (!navigator.geolocation) {
      elements.errorMessage.textContent = "이 브라우저는 현재 위치 조회를 지원하지 않습니다.";
      setScreen("error");
      return;
    }
    elements.useLocation.disabled = true;
    elements.useLocation.lastChild.textContent = " 위치 확인 중";
    navigator.geolocation.getCurrentPosition(
      (position) => {
        resetFields();
        setActiveChip(null);
        elements.useLocation.disabled = false;
        elements.useLocation.lastChild.textContent = " 내 주변 장소 찾기";
        loadPlaces(
          makeNearbyRequest(
            position.coords.latitude,
            position.coords.longitude,
            10,
            "내 위치 반경 10km",
          ),
        );
      },
      (error) => {
        elements.useLocation.disabled = false;
        elements.useLocation.lastChild.textContent = " 내 주변 장소 찾기";
        const messages = {
          1: "위치 권한이 필요합니다. 브라우저 설정에서 위치 접근을 허용해주세요.",
          2: "현재 위치를 확인할 수 없습니다.",
          3: "현재 위치 확인 시간이 초과되었습니다.",
        };
        elements.errorMessage.textContent = messages[error.code] || "현재 위치를 확인하지 못했습니다.";
        setScreen("error");
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 },
    );
  }

  elements.form.addEventListener("submit", (event) => {
    event.preventDefault();
    setActiveChip(null);
    loadPlaces(makeListRequest({ context: "검색 결과" }));
  });

  elements.chips.forEach((chip) => {
    chip.addEventListener("click", () => {
      const action = chip.dataset.action;
      resetFields();
      setActiveChip(action);
      if (action === "seoul") {
        elements.region.value = "11";
        loadPlaces(makeListRequest({ context: "서울 장소" }));
      } else if (action === "with-crowd") {
        loadPlaces(makeListRequest({ context: "혼잡도 제공 장소", onlyWithCrowd: true }));
      } else if (action === "palace-nearby") {
        loadPlaces(
          makeNearbyRequest(
            PALACE_CENTER.latitude,
            PALACE_CENTER.longitude,
            PALACE_CENTER.radiusKm,
            "경복궁 반경 3km",
          ),
        );
      } else {
        loadPlaces(makeListRequest({ context: "전국 장소" }));
      }
    });
  });

  elements.refresh.addEventListener("click", () => {
    loadPlaces(state.lastRequest || makeListRequest({ context: "전국 장소" }), { remember: false });
  });
  elements.retry.addEventListener("click", () => {
    loadPlaces(state.lastRequest || makeListRequest({ context: "전국 장소" }), { remember: false });
  });
  elements.useLocation.addEventListener("click", useCurrentLocation);
  elements.closeDetail.addEventListener("click", () => elements.dialog.close());
  elements.dialog.addEventListener("click", (event) => {
    if (event.target === elements.dialog) elements.dialog.close();
  });
  elements.dialog.addEventListener("close", () => {
    if (state.detailController) state.detailController.abort();
  });

  checkHealth();
  loadPlaces(makeListRequest({ context: "전국 장소" }));
})();
