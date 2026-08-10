// ==========================================
// БЛОК 1: ИНИЦИАЛИЗАЦИЯ
// ==========================================
const map = L.map("map", { zoomControl: false, minZoom: 3, maxZoom: 18 }).setView([52.03, 117.5], 6);
L.control.zoom({ position: "bottomleft" }).addTo(map);

const basemaps = {
  gis2: L.tileLayer("https://tile{s}.maps.2gis.com/tiles?x={x}&y={y}&z={z}&v=1", { subdomains: ["0", "1", "2", "3"], attribution: "&copy; 2GIS", noWrap: true, maxZoom: 19, zIndex: 1 }).addTo(map),
  esri: L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", { attribution: "&copy; Esri", maxZoom: 19, noWrap: true, zIndex: 1 }),
};

document.querySelectorAll('input[name="basemap"]').forEach((radio) => {
  radio.addEventListener("change", (e) => {
    Object.values(basemaps).forEach((layer) => map.removeLayer(layer));
    map.addLayer(basemaps[e.target.value]);
  });
});

const nextgisBaseUrl = "https://nextgis.tsugeoprognoz.ru";

// ==========================================
// БЛОК 2: ОБЫЧНЫЕ ПОЛИГОНЫ И ЛИНИИ (Всегда картинки TMS)
// ==========================================
function createNextGisLayer(resourceId, layerZIndex = 10) {
  return L.tileLayer(`${nextgisBaseUrl}/api/component/render/tile?resource=${resourceId}&nd=204&z={z}&x={x}&y={y}`, {
    transparent: true, format: 'image/png', noWrap: true, zIndex: layerZIndex
  });
}

function setupLayerToggle(checkboxId, leafletLayer) {
  const checkbox = document.getElementById(checkboxId);
  if (!checkbox) return; 
  if (checkbox.checked) map.addLayer(leafletLayer);
  checkbox.addEventListener("change", (e) => {
    if (e.target.checked) map.addLayer(leafletLayer);
    else map.removeLayer(leafletLayer);
  });
}

const layerGrid200k = createNextGisLayer(321, 10); setupLayerToggle("chkGrid200k", layerGrid200k);
const layerGrid1M = createNextGisLayer(323, 10); setupLayerToggle("chkGrid1M", layerGrid1M);
const layerRailRoads = createNextGisLayer(327, 50); setupLayerToggle("chkRailRoads", layerRailRoads);
const layerAutoRoads = createNextGisLayer(329, 40); setupLayerToggle("chkAutoRoads", layerAutoRoads);
const layerRivers = createNextGisLayer(331, 30); setupLayerToggle("chkRivers", layerRivers);
const layerLabels = createNextGisLayer(339, 50); setupLayerToggle("chkLabels", layerLabels);
const layerSubjBorder = createNextGisLayer(333, 20); setupLayerToggle("chkSubjBorder", layerSubjBorder);
const layerGovBorder = createNextGisLayer(335, 20); setupLayerToggle("chkGovBorder", layerGovBorder);
const layerBorderKant = createNextGisLayer(337, 10); setupLayerToggle("chkBorderKant", layerBorderKant);

const layerOreNodes = createNextGisLayer(341, 10); setupLayerToggle("chkOreNodes", layerOreNodes);
const layerOreRegions = createNextGisLayer(343, 10); setupLayerToggle("chkOreRegions", layerOreRegions);

const layerBeExt = createNextGisLayer(359, 10); setupLayerToggle("chkBeExt", layerBeExt);
const layerBeInt = createNextGisLayer(361, 10); setupLayerToggle("chkBeInt", layerBeInt);
const layerBiExt = createNextGisLayer(365, 10); setupLayerToggle("chkBiExt", layerBiExt);
const layerBiInt = createNextGisLayer(367, 10); setupLayerToggle("chkBiInt", layerBiInt);
const layerWExt = createNextGisLayer(371, 10); setupLayerToggle("chkWExt", layerWExt);
const layerWInt = createNextGisLayer(373, 10); setupLayerToggle("chkWInt", layerWInt);
const layerGeExt = createNextGisLayer(377, 10); setupLayerToggle("chkGeExt", layerGeExt);
const layerGeInt = createNextGisLayer(379, 10); setupLayerToggle("chkGeInt", layerGeInt);
const layerAuExt = createNextGisLayer(382, 10); setupLayerToggle("chkAuExt", layerAuExt);
const layerAuInt = createNextGisLayer(384, 10); setupLayerToggle("chkAuInt", layerAuInt);
const layerLiExt = createNextGisLayer(389, 10); setupLayerToggle("chkLiExt", layerLiExt);
const layerLiInt = createNextGisLayer(391, 10); setupLayerToggle("chkLiInt", layerLiInt);
const layerCuExt = createNextGisLayer(395, 10); setupLayerToggle("chkCuExt", layerCuExt);
const layerCuInt = createNextGisLayer(397, 10); setupLayerToggle("chkCuInt", layerCuInt);
const layerMoExt = createNextGisLayer(401, 10); setupLayerToggle("chkMoExt", layerMoExt);
const layerMoInt = createNextGisLayer(403, 10); setupLayerToggle("chkMoInt", layerMoInt);
const layerAsExt = createNextGisLayer(407, 10); setupLayerToggle("chkAsExt", layerAsExt);
const layerAsInt = createNextGisLayer(409, 10); setupLayerToggle("chkAsInt", layerAsInt);
const layerSnExt = createNextGisLayer(413, 10); setupLayerToggle("chkSnExt", layerSnExt);
const layerSnInt = createNextGisLayer(415, 10); setupLayerToggle("chkSnInt", layerSnInt);
const layerPbZnExt = createNextGisLayer(419, 10); setupLayerToggle("chkPbZnExt", layerPbZnExt);
const layerPbZnInt = createNextGisLayer(421, 10); setupLayerToggle("chkPbZnInt", layerPbZnInt);
const layerSbExt = createNextGisLayer(425, 10); setupLayerToggle("chkSbExt", layerSbExt);
const layerSbInt = createNextGisLayer(427, 10); setupLayerToggle("chkSbInt", layerSbInt);
const layerTaNbExt = createNextGisLayer(431, 10); setupLayerToggle("chkTaNbExt", layerTaNbExt);
const layerTaNbInt = createNextGisLayer(433, 10); setupLayerToggle("chkTaNbInt", layerTaNbInt);
const layerUExt = createNextGisLayer(437, 10); setupLayerToggle("chkUExt", layerUExt);
const layerUInt = createNextGisLayer(439, 10); setupLayerToggle("chkUInt", layerUInt);

const layerFaults1M = createNextGisLayer(441, 40); setupLayerToggle("chkFaults1M", layerFaults1M);
const layerGeoMap1M = createNextGisLayer(443, 5); setupLayerToggle("chkGeoMap1M", layerGeoMap1M);
const layerEmag = createNextGisLayer(445, 5); setupLayerToggle("chkEmag", layerEmag);
const layerWgm = createNextGisLayer(447, 5); setupLayerToggle("chkWgm", layerWgm);
const layerDemColor = createNextGisLayer(449, 5); setupLayerToggle("chkDemColor", layerDemColor);
const layerDem300m = createNextGisLayer(451, 5); setupLayerToggle("chkDem300m", layerDem300m);

// ==========================================
// БЛОК 3: ГИБРИДНЫЕ СЛОИ ДЛЯ ТОЧЕК (Кластеры <-> Картинки)
// ==========================================
function setupHybridPointLayer(checkboxId, styleId, vectorId, switchZoom = 9) {
  const chk = document.getElementById(checkboxId);
  if (!chk) return;

  // Слой 1: Идеальные картинки из QGIS
  const tmsLayer = L.tileLayer(`${nextgisBaseUrl}/api/component/render/tile?resource=${styleId}&nd=204&z={z}&x={x}&y={y}`, {
    transparent: true, format: 'image/png', noWrap: true, zIndex: 70
  });

  // Слой 2: Кластеры
  const clusterGroup = L.markerClusterGroup({ maxClusterRadius: 50 });
  let isVectorLoaded = false;

  async function loadVector() {
    if (isVectorLoaded) return;
    try {
      const label = chk.nextElementSibling;
      const originalText = label.innerHTML;
      label.innerHTML = `<span class="spinner-border spinner-border-sm text-primary me-1" role="status" aria-hidden="true"></span> ${originalText}`;

      const response = await fetch(`${nextgisBaseUrl}/api/resource/${vectorId}/geojson?srs=4326`);
      const data = await response.json();

      if (data && data.features) {
        const geoJsonLayer = L.geoJSON(data, {
          coordsToLatLng: function (coords) {
            if (Math.abs(coords[0]) > 180 || Math.abs(coords[1]) > 90) {
              const pt = L.point(coords[0], coords[1]);
              return L.CRS.EPSG3857.unproject(pt); 
            }
            return new L.LatLng(coords[1], coords[0]);
          },
          pointToLayer: function (feature, latlng) {
            return L.circleMarker(latlng, { radius: 5, fillColor: "#6c757d", color: "#ffffff", weight: 1, opacity: 1, fillOpacity: 0.9 });
          }
        });
        clusterGroup.addLayer(geoJsonLayer);
      }
      isVectorLoaded = true;
      label.innerHTML = originalText;
    } catch (e) {
      console.error(`Ошибка гибридного слоя ${vectorId}:`, e);
      chk.checked = false;
    }
  }

  function updateVisibility() {
    if (!chk.checked) {
      map.removeLayer(tmsLayer);
      map.removeLayer(clusterGroup);
      return;
    }
    if (map.getZoom() < switchZoom) {
      map.removeLayer(tmsLayer);
      map.addLayer(clusterGroup);
      if (!isVectorLoaded) loadVector();
    } else {
      map.removeLayer(clusterGroup);
      map.addLayer(tmsLayer);
    }
  }

  chk.addEventListener("change", updateVisibility);
  map.on('zoomend', updateVisibility);
  if (chk.checked) updateVisibility();
}

// ВОЗВРАЩАЕМ ТОЧКИ К ЖИЗНИ!
setupHybridPointLayer("chkCities", 325, 324, 9);
setupHybridPointLayer("chkMetalsDeposits", 345, 344, 9);
setupHybridPointLayer("chkMetalsOccurrences", 347, 346, 9);
setupHybridPointLayer("chkMetalsPoints", 349, 348, 9);
setupHybridPointLayer("chkNonMetalsDeposits", 351, 350, 9);
setupHybridPointLayer("chkNonMetalsOccurrences", 353, 352, 9);
setupHybridPointLayer("chkNonMetalsPoints", 355, 354, 9);

setupHybridPointLayer("chkBeDep", 357, 356, 9);
setupHybridPointLayer("chkBiDep", 363, 362, 9);
setupHybridPointLayer("chkWDep", 369, 368, 9);
setupHybridPointLayer("chkGeDep", 375, 374, 9);
setupHybridPointLayer("chkAuDep", 381, 380, 9);
setupHybridPointLayer("chkLiDep", 387, 386, 9);
setupHybridPointLayer("chkCuDep", 393, 392, 9);
setupHybridPointLayer("chkMoDep", 399, 398, 9);
setupHybridPointLayer("chkAsDep", 405, 404, 9);
setupHybridPointLayer("chkSnDep", 411, 410, 9);
setupHybridPointLayer("chkPbZnDep", 417, 416, 9);
setupHybridPointLayer("chkSbDep", 423, 422, 9);
setupHybridPointLayer("chkTaNbDep", 429, 428, 9);
setupHybridPointLayer("chkUDep", 435, 434, 9);


// ==========================================
// БЛОК 4: ИНТЕРФЕЙС И ГРУППИРОВКИ
// ==========================================
const sidebar = document.getElementById("layersSidebar");
const btnCollapse = document.getElementById("layersSidebarCollapse");
const iconToggle = document.getElementById("layerToggleIcon");

btnCollapse.addEventListener("click", () => {
  sidebar.classList.toggle("collapsed");
  iconToggle.className = sidebar.classList.contains("collapsed") ? "bi bi-chevron-right" : "bi bi-chevron-left";
  setTimeout(() => map.invalidateSize(), 300);
});

document.querySelectorAll('button[data-bs-toggle="collapse"]').forEach(btn => {
  const targetId = btn.getAttribute('data-bs-target');
  const folderContent = targetId ? document.querySelector(targetId) : null;
  if (!folderContent) return;

  const masterCheck = document.createElement('input');
  masterCheck.type = 'checkbox';
  masterCheck.className = 'form-check-input me-3';
  masterCheck.style.cssText = 'margin-top: 2px; margin-left: -5px;';
  masterCheck.title = 'Включить/выключить все слои в папке';

  masterCheck.addEventListener('click', (e) => e.stopPropagation());
  masterCheck.addEventListener('change', (e) => {
    const isChecked = e.target.checked;
    folderContent.querySelectorAll('.layer-item input[type="checkbox"]:not([disabled])').forEach(chk => {
      if (chk.checked !== isChecked) {
        chk.checked = isChecked;
        chk.dispatchEvent(new Event('change')); 
      }
    });
  });

  const titleSpan = btn.querySelector('span');
  if (titleSpan) {
    titleSpan.classList.add('d-flex', 'align-items-center');
    titleSpan.prepend(masterCheck);
  }
});

document.querySelectorAll('.accordion-body .fw-bold.text-secondary').forEach(header => {
  header.classList.add('d-flex', 'align-items-center');
  const subCheck = document.createElement('input');
  subCheck.type = 'checkbox';
  subCheck.className = 'form-check-input me-2 mb-0';
  subCheck.style.cssText = 'margin-top: 0; margin-left: -15px;';
  
  subCheck.addEventListener('change', (e) => {
    const isChecked = e.target.checked;
    let nextEl = header.nextElementSibling;
    while (nextEl && !nextEl.classList.contains('fw-bold')) {
      if (nextEl.classList.contains('layer-item')) {
        const chk = nextEl.querySelector('input[type="checkbox"]:not([disabled])');
        if (chk && chk.checked !== isChecked) {
          chk.checked = isChecked;
          chk.dispatchEvent(new Event('change'));
        }
      }
      nextEl = nextEl.nextElementSibling;
    }
  });
  header.prepend(subCheck);
});

// ==========================================
// БЛОК 5: BBOX КЛИК И ПРАВЫЕ ТАБЛИЦЫ
// ==========================================
const queryQueue = [
  { chkId: "chkCities", vectorId: 324, delta: 3000 }, 
  { chkId: "chkLabels", vectorId: 338, delta: 3000 }, 
  { chkId: "chkMetalsDeposits", vectorId: 344, delta: 3000 }, 
  { chkId: "chkMetalsOccurrences", vectorId: 346, delta: 3000 }, 
  { chkId: "chkMetalsPoints", vectorId: 348, delta: 3000 }, 
  { chkId: "chkNonMetalsDeposits", vectorId: 350, delta: 3000 }, 
  { chkId: "chkNonMetalsOccurrences", vectorId: 352, delta: 3000 }, 
  { chkId: "chkNonMetalsPoints", vectorId: 354, delta: 3000 }, 
  { chkId: "chkBeDep", vectorId: 356, delta: 5000 }, { chkId: "chkBiDep", vectorId: 362, delta: 5000 },
  { chkId: "chkWDep", vectorId: 368, delta: 5000 }, { chkId: "chkGeDep", vectorId: 374, delta: 5000 },
  { chkId: "chkAuDep", vectorId: 380, delta: 5000 }, { chkId: "chkLiDep", vectorId: 386, delta: 5000 },
  { chkId: "chkCuDep", vectorId: 392, delta: 5000 }, { chkId: "chkMoDep", vectorId: 398, delta: 5000 },
  { chkId: "chkAsDep", vectorId: 404, delta: 5000 }, { chkId: "chkSnDep", vectorId: 410, delta: 5000 },
  { chkId: "chkPbZnDep", vectorId: 416, delta: 5000 }, { chkId: "chkSbDep", vectorId: 422, delta: 5000 },
  { chkId: "chkTaNbDep", vectorId: 428, delta: 5000 }, { chkId: "chkUDep", vectorId: 434, delta: 5000 },
  { chkId: "chkRivers", vectorId: 330, delta: 1000 }, { chkId: "chkRailRoads", vectorId: 326, delta: 1000 }, 
  { chkId: "chkAutoRoads", vectorId: 328, delta: 1000 }, { chkId: "chkBorderKant", vectorId: 336, delta: 1000 }, 
  { chkId: "chkFaults1M", vectorId: 440, delta: 1000 }, { chkId: "chkGrid200k", vectorId: 320, delta: 100 }, 
  { chkId: "chkGrid1M", vectorId: 322, delta: 100 }, { chkId: "chkSubjBorder", vectorId: 332, delta: 100 }, 
  { chkId: "chkGovBorder", vectorId: 334, delta: 100 }, { chkId: "chkOreNodes", vectorId: 340, delta: 100 }, 
  { chkId: "chkOreRegions", vectorId: 342, delta: 100 }, { chkId: "chkGeoMap1M", vectorId: 442, delta: 100 } 
];

map.on('click', async function(e) {
  const point = L.CRS.EPSG3857.project(e.latlng);
  const activeLayers = queryQueue.filter(layer => {
    const checkbox = document.getElementById(layer.chkId);
    return checkbox && checkbox.checked;
  });

  if (activeLayers.length === 0) return;

  for (const layer of activeLayers) {
    const d = layer.delta; 
    const bbox = `${point.x - d} ${point.y - d}, ${point.x + d} ${point.y - d}, ${point.x + d} ${point.y + d}, ${point.x - d} ${point.y + d}, ${point.x - d} ${point.y - d}`;
    const wktPolygon = `POLYGON((${bbox}))`;
    const url = `${nextgisBaseUrl}/api/resource/${layer.vectorId}/feature/?intersects=${encodeURIComponent(wktPolygon)}&geom=no`;
    
    try {
      const response = await fetch(url);
      const data = await response.json();

      if (data && data.length > 0) {
        const props = data[0].fields;
        let popupContent = `<div style="min-width: 200px;">
                              <h6 class="fw-bold mb-2 border-bottom pb-1" style="color: var(--geo-main);">
                                <i class="bi bi-info-circle me-1" style="color: var(--geo-accent);"></i> Информация об объекте
                              </h6>
                              <table class="table table-sm table-bordered table-striped mb-0" style="font-size: 0.8rem;"><tbody>`;
        
        for (const key in props) {
          if (props[key] !== null && props[key] !== '') {
              popupContent += `<tr><td class="text-muted fw-bold w-50">${key}</td><td>${props[key]}</td></tr>`;
          }
        }
        popupContent += `</tbody></table></div>`;
        L.popup({ maxWidth: 400 }).setLatLng(e.latlng).setContent(popupContent).openOn(map);
        break; 
      }
    } catch(err) {
      console.error(`Ошибка при запросе к слою ${layer.vectorId}:`, err);
    }
  }
});

const attrSidebar = document.getElementById('attributeSidebar');
const closeAttrBtn = document.getElementById('closeAttributeSidebar');
const attrContainer = document.getElementById('attributeTableContainer');
closeAttrBtn.addEventListener('click', () => attrSidebar.classList.remove('open'));

async function loadAttributeTable(vectorId, layerName) {
  attrSidebar.classList.add('open');
  attrContainer.innerHTML = `<div class="text-center mt-5">
                                <div class="spinner-border" style="color: var(--geo-main);" role="status"></div>
                                <div class="mt-2 text-muted">Стягиваем данные с NextGIS...</div>
                             </div>`;

  try {
    const response = await fetch(`${nextgisBaseUrl}/api/resource/${vectorId}/feature/?geom=no`);
    const data = await response.json();

    if (!data || data.length === 0) {
      attrContainer.innerHTML = `<div class="alert alert-warning mt-3">Слой пуст или данных нет.</div>`;
      return;
    }

    const firstProps = data[0].fields;
    let tableHTML = `<h6 class="text-secondary mb-2 fw-bold">${layerName} (Записей: ${data.length})</h6>
                     <table class="table table-sm table-bordered table-striped" style="font-size: 0.75rem;"><thead class="table-light"><tr>`;
    
    for (const key in firstProps) tableHTML += `<th>${key}</th>`;
    tableHTML += `</tr></thead><tbody>`;

    const limit = Math.min(data.length, 500); 
    for (let i = 0; i < limit; i++) {
      tableHTML += `<tr>`;
      for (const key in firstProps) {
        let val = data[i].fields[key];
        tableHTML += `<td>${(val !== null && val !== undefined) ? val : ''}</td>`;
      }
      tableHTML += `</tr>`;
    }
    tableHTML += `</tbody></table>`;
    if (data.length > 500) tableHTML += `<div class="text-muted small mt-2">* Показаны только первые 500 записей.</div>`;
    attrContainer.innerHTML = tableHTML;
  } catch(err) {
    attrContainer.innerHTML = `<div class="alert alert-danger mt-3">Ошибка загрузки данных.</div>`;
  }
}

queryQueue.forEach(layer => {
  const checkbox = document.getElementById(layer.chkId);
  if (checkbox) {
    const layerItem = checkbox.closest('.layer-item');
    if (layerItem) {
      layerItem.classList.add('d-flex', 'align-items-center');
      const label = layerItem.querySelector('label');
      const layerName = label ? label.innerText.trim() : 'Слой';
      const btn = document.createElement('button');
      btn.className = "btn btn-sm btn-link p-0 ms-auto text-secondary";
      btn.title = "Открыть таблицу атрибутов";
      btn.innerHTML = `<i class="bi bi-table"></i>`; 
      btn.addEventListener('click', (e) => {
        e.preventDefault(); e.stopPropagation();
        loadAttributeTable(layer.vectorId, layerName);
      });
      layerItem.appendChild(btn);
    }
  }
});