/**
 * ГЛАВНЫЙ СКРИПТ КАРТЫ (ГИС Забайкальского края)
 * Разработка: Лаборатория ГИС
 */

// ==========================================
// БЛОК 1: ИНИЦИАЛИЗАЦИЯ КАРТЫ И БАЗОВЫХ СЛОЕВ
// ==========================================

const nextgisBaseUrl = "";

const map = L.map("map", { zoomControl: false, minZoom: 3, maxZoom: 18 }).setView([52.03, 117.5], 6);
L.control.zoom({ position: "bottomleft" }).addTo(map);
// Добавляем классическую линейку масштаба в правый нижний угол
L.control.scale({ position: 'bottomright', metric: true, imperial: false }).addTo(map);

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

// ==========================================
// БЛОК 2: АРХИТЕКТУРА ИНТЕРФЕЙСА (ПАПКИ И ГАЛОЧКИ)
// ==========================================
const sidebar = document.getElementById("layersSidebar");
const btnCollapse = document.getElementById("layersSidebarCollapse");
const iconToggle = document.getElementById("layerToggleIcon");

// ----- НОВЫЙ МОБИЛЬНЫЙ КУСОК -----
// Если зашли с телефона, сразу прячем меню при загрузке
if (window.innerWidth <= 768) {
  sidebar.classList.add("collapsed");
  if (iconToggle) iconToggle.className = "bi bi-chevron-right";
}
// ---------------------------------

if (btnCollapse) {
  btnCollapse.addEventListener("click", () => {
    sidebar.classList.toggle("collapsed");
    iconToggle.className = sidebar.classList.contains("collapsed") ? "bi bi-chevron-right" : "bi bi-chevron-left";
    setTimeout(() => map.invalidateSize(), 300);
  });
}

// ----- НОВЫЙ МОБИЛЬНЫЙ КУСОК -----
// Если на телефоне человек тапнул по карте — меню прячется само
map.on('click', () => {
  if (window.innerWidth <= 768 && !sidebar.classList.contains("collapsed")) {
    sidebar.classList.add("collapsed");
    if (iconToggle) iconToggle.className = "bi bi-chevron-right";
  }
});
// ---------------------------------

// ==========================================
// УТИЛИТА: ПРОВЕРКА ВИДИМОСТИ ПАПКИ
// ==========================================
// Железобетонная функция проверки: включен ли рубильник у папки слоя?
function isFolderChecked(chk) {
  const folder = chk.closest('.collapse');
  if (!folder) return true; // Если слой без папки
  
  const container = folder.parentElement;
  const masterCheck = container.querySelector('.folder-master-checkbox');
  return masterCheck ? masterCheck.checked : true;
}

// ==========================================
// ДИНАМИЧЕСКИЙ ДВИЖОК СЛОЕВ И ПЕРЕХВАТ 403
// ==========================================

// Очередь для BBOX-запросов (формируется автоматически)
let dynamicQueryQueue = [];

// Тост-уведомление для 403 ошибки
function showForbiddenToast(layerName = 'Запрошенный слой') {
    let toastContainer = document.getElementById('geo-toast-container');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.id = 'geo-toast-container';
        toastContainer.className = 'toast-container position-fixed bottom-0 end-0 p-3';
        toastContainer.style.zIndex = '9999';
        document.body.appendChild(toastContainer);
    }
    
    const toastHtml = `
        <div class="toast align-items-center text-bg-danger border-0 show" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body fw-medium">
                    <i class="bi bi-shield-lock-fill me-2"></i> Нет доступа к дата-руму:<br><small>${layerName}</small>
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close" onclick="this.closest('.toast').remove()"></button>
            </div>
        </div>`;
    toastContainer.insertAdjacentHTML('beforeend', toastHtml);
    setTimeout(() => { if (toastContainer.lastChild) toastContainer.lastChild.remove(); }, 4000);
}

// Генерация UI на лету из JSON (Скрываем недоступные слои и пустые папки)
async function initDynamicLayers() {
    try {
        const response = await fetch('/api/layers_config');
        if (!response.ok) throw new Error('Ошибка загрузки конфига');
        const config = await response.json();
        
        const container = document.getElementById('layersAccordion');
        container.innerHTML = ''; 

        let folderIndex = 0;

        for (const [categoryName, subcategories] of Object.entries(config)) {
            folderIndex++;
            const folderId = `dyn_folder_${folderIndex}`;
            
            let categoryHtmlContent = "";
            let hasAnyLayerInCategory = false; // Флаг: есть ли в этой папке хоть что-то доступное?

            for (const [subName, layers] of Object.entries(subcategories)) {
                let subcategoryHtmlContent = "";
                let hasAnyLayerInSub = false; // Флаг: есть ли доступное в этой подгруппе?

                for (const [layerName, ids] of Object.entries(layers)) {
                    const vectorId = ids[0];
                    const rasterId = ids[1] || ids[0];
                    const chkId = `chk_${rasterId}`;
                    
                    // ПРОВЕРКА ПРАВ: Если "*", то можно всё. Иначе ищем ID в массиве.
                    const isAllowed = userAllowedLayers === "*" || userAllowedLayers.includes(rasterId) || userAllowedLayers.includes(vectorId);

                    // ЕСЛИ ДОСТУП ЕСТЬ — ГЕНЕРИМ СЛОЙ
                    if (isAllowed) {
                        hasAnyLayerInSub = true;
                        hasAnyLayerInCategory = true;
                        
                        const isPointLayer = categoryName.includes('Полезные ископаемые') || categoryName.includes('Экстенсивность') || subName.includes('Населённые пункты');
                        const delta = isPointLayer ? 5000 : 1000;
                        
                        dynamicQueryQueue.push({ chkId: chkId, vectorId: vectorId, delta: delta, name: layerName });

                        subcategoryHtmlContent += `
                        <div class="form-check layer-item d-flex align-items-center">
                            <input class="form-check-input dyn-layer-chk" type="checkbox" id="${chkId}" data-vector="${vectorId}" data-raster="${rasterId}" data-name="${layerName}" data-hybrid="${isPointLayer}">
                            <label class="form-check-label w-100" for="${chkId}">${layerName}</label>
                            <button class="btn btn-sm btn-link p-0 ms-auto text-secondary attr-btn" title="Таблица атрибутов" data-vid="${vectorId}" data-lname="${layerName}">
                                <i class="bi bi-table"></i>
                            </button>
                        </div>`;
                    }
                }

                // ВАЖНО: Рисуем заголовок подгруппы (например "Металлические ископаемые"), 
                // ТОЛЬКО если в ней сгенерировался хотя бы один слой
                if (hasAnyLayerInSub) {
                    categoryHtmlContent += `
                    <div class="fw-bold mt-2 mb-1 ms-2 small text-secondary d-flex align-items-center">
                        <input type="checkbox" class="form-check-input me-2 mb-0 sub-master-checkbox" style="margin-top: 0; margin-left: -15px; cursor: pointer;" title="Выбрать подгруппу">
                        ${subName}
                    </div>` + subcategoryHtmlContent;
                }
            }

            // ВАЖНО: Рисуем саму папку (аккордеон), ТОЛЬКО если в ней есть доступные данные
            if (hasAnyLayerInCategory) {
                let html = `
                <div class="border rounded-3 bg-light p-2 mb-2">
                    <div class="d-flex align-items-center w-100">
                        <input type="checkbox" class="form-check-input ms-2 me-2 folder-master-checkbox" checked style="cursor: pointer;" title="Включить/скрыть папку">
                        <button class="btn btn-link btn-sm text-start d-flex justify-content-between align-items-center text-decoration-none fw-bold text-dark ps-2" type="button" data-bs-toggle="collapse" data-bs-target="#${folderId}" style="flex-grow: 1;">
                            <span><i class="bi bi-folder2-open me-2" style="color: var(--geo-main);"></i>${categoryName}</span>
                            <i class="bi bi-chevron-down small text-muted toggle-arrow"></i>
                        </button>
                    </div>
                    <div id="${folderId}" class="accordion-collapse collapse">
                        <div class="accordion-body p-2 d-flex flex-column gap-1">
                            ${categoryHtmlContent}
                        </div>
                    </div>
                </div>`;
                container.insertAdjacentHTML('beforeend', html);
            }
        }

        bindDynamicLogic();

    } catch (error) {
        console.error("Сбой сборки меню:", error);
    }
}

// Привязка картографии к сгенерированным чекбоксам
function bindDynamicLogic() {
    // 1. Оживляем рубильники папок
    document.querySelectorAll('.folder-master-checkbox').forEach(master => {
        master.addEventListener('change', (e) => {
            const folder = e.target.closest('.border').querySelector('.collapse');
            folder.querySelectorAll('.dyn-layer-chk').forEach(chk => {
                chk.dispatchEvent(new Event('folderToggled'));
            });
        });
    });

    // Оживляем рубильники подгрупп
    document.querySelectorAll('.sub-master-checkbox').forEach(sub => {
        sub.addEventListener('change', (e) => {
            const isChecked = e.target.checked;
            let nextEl = e.target.parentElement.nextElementSibling;
            while (nextEl && !nextEl.classList.contains('fw-bold')) {
                if (nextEl.classList.contains('layer-item')) {
                    const chk = nextEl.querySelector('.dyn-layer-chk');
                    if (chk && chk.checked !== isChecked) {
                        chk.checked = isChecked;
                        chk.dispatchEvent(new Event('change'));
                    }
                }
                nextEl = nextEl.nextElementSibling;
            }
        });
    });

    // 2. Создаем сами слои Leaflet
    document.querySelectorAll('.dyn-layer-chk').forEach(chk => {
        const rasterId = chk.getAttribute('data-raster');
        const vectorId = chk.getAttribute('data-vector');
        const layerName = chk.getAttribute('data-name');
        const isHybrid = chk.getAttribute('data-hybrid') === 'true';
        const switchZoom = 9;
        
        // Создаем растровый слой (картинка)
        const tmsLayer = L.tileLayer(`${nextgisBaseUrl}/api/component/render/tile?resource=${rasterId}&nd=204&z={z}&x={x}&y={y}`, {
            transparent: true, format: 'image/png', noWrap: true, zIndex: isHybrid ? 70 : 10
        });

        // ПЕРЕХВАТ 403 ДЛЯ КАРТЫ: Если тайл не загрузился из-за прав доступа
        tmsLayer.on('tileerror', function() {
            if (!chk.dataset.errorShown) {
                showForbiddenToast(layerName);
                chk.dataset.errorShown = "true"; 
                setTimeout(() => chk.dataset.errorShown = "false", 10000); // Глушим спам тостов на 10 сек
                chk.checked = false; // Отщелкиваем галочку
                if (map.hasLayer(tmsLayer)) map.removeLayer(tmsLayer);
            }
        });

        // Логика для кластеров (если слой помечен как гибридный)
        let clusterGroup = null;
        let isVectorLoaded = false;
        
        if (isHybrid) {
            clusterGroup = L.markerClusterGroup({ maxClusterRadius: 50 });
        }

        async function loadHybridVector() {
            if (isVectorLoaded || !isHybrid) return;
            try {
                const response = await fetch(`${nextgisBaseUrl}/api/resource/${vectorId}/geojson?srs=4326`);
                if (response.status === 403) {
                    showForbiddenToast(layerName);
                    chk.checked = false;
                    return;
                }
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
            } catch (e) {
                console.error("Ошибка вектора:", e);
                chk.checked = false;
            }
        }

        function updateVisibility() {
            if (!(chk.checked && isFolderChecked(chk))) {
                if (map.hasLayer(tmsLayer)) map.removeLayer(tmsLayer);
                if (isHybrid && map.hasLayer(clusterGroup)) map.removeLayer(clusterGroup);
                return;
            }
            
            // Если слой гибридный — включаем логику кластеров
            if (isHybrid) {
                if (map.getZoom() < switchZoom) {
                    if (map.hasLayer(tmsLayer)) map.removeLayer(tmsLayer);
                    if (!map.hasLayer(clusterGroup)) map.addLayer(clusterGroup);
                    if (!isVectorLoaded) loadHybridVector();
                } else {
                    if (map.hasLayer(clusterGroup)) map.removeLayer(clusterGroup);
                    if (!map.hasLayer(tmsLayer)) map.addLayer(tmsLayer);
                }
            } else {
                // Обычный слой (просто показываем картинку)
                if (!map.hasLayer(tmsLayer)) map.addLayer(tmsLayer);
            }
        }

        chk.addEventListener("change", updateVisibility);
        chk.addEventListener("folderToggled", updateVisibility);
        if (isHybrid) map.on('zoomend', updateVisibility);
    });
    
    // 3. Перехват 403 для кнопок таблиц атрибутов
    document.querySelectorAll('.attr-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.preventDefault();
            const vid = btn.getAttribute('data-vid');
            const lname = btn.getAttribute('data-lname');
            
            // Быстрая проверка прав перед загрузкой огромной таблицы
            const testResponse = await fetch(`${nextgisBaseUrl}/api/resource/${vid}/feature/?geom=no&limit=1`);
            if (testResponse.status === 403) {
                showForbiddenToast(lname);
                return;
            }
            loadAttributeTable(vid, lname);
        });
    });
}

// Запускаем сборку интерфейса
initDynamicLayers();

// ==========================================
// БЛОК 5: BBOX КЛИК И ПРАВЫЕ ТАБЛИЦЫ
// ==========================================

map.on('click', async function(e) {
    const point = L.CRS.EPSG3857.project(e.latlng);
    
    // Берем активные слои из динамической очереди
    let activeLayers = dynamicQueryQueue.filter(layer => {
        const checkbox = document.getElementById(layer.chkId);
        return checkbox && checkbox.checked && isFolderChecked(checkbox);
    });

    if (activeLayers.length === 0) return;

    // СОРТИРОВКА: Сначала проверяем точечные слои (delta=5000), потом полигоны
    activeLayers.sort((a, b) => b.delta - a.delta);

    for (const layer of activeLayers) {
        const d = layer.delta; 
        const bbox = `${point.x - d} ${point.y - d}, ${point.x + d} ${point.y - d}, ${point.x + d} ${point.y + d}, ${point.x - d} ${point.y + d}, ${point.x - d} ${point.y - d}`;
        const wktPolygon = `POLYGON((${bbox}))`;
        const url = `${nextgisBaseUrl}/api/resource/${layer.vectorId}/feature/?intersects=${encodeURIComponent(wktPolygon)}&geom=no`;
        
        try {
            const response = await fetch(url);
            
            // ПЕРЕХВАТ 403 ДЛЯ BBOX
            if (response.status === 403) {
                showForbiddenToast(layer.name);
                continue; // Пропускаем этот слой и ищем дальше
            }
            
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
                break; // Нашли объект — обрываем цикл
            }
        } catch(err) {
            console.error(`Ошибка при запросе к слою ${layer.vectorId}:`, err);
        }
    }
});

const attrSidebar = document.getElementById('attributeSidebar');
const closeAttrBtn = document.getElementById('closeAttributeSidebar');
const attrContainer = document.getElementById('attributeTableContainer');

if(closeAttrBtn) {
  closeAttrBtn.addEventListener('click', () => attrSidebar.classList.remove('open'));
}

async function loadAttributeTable(vectorId, layerName) {
  if(attrSidebar) attrSidebar.classList.add('open');
  if(attrContainer) attrContainer.innerHTML = `<div class="text-center mt-5">
                                                  <div class="spinner-border" style="color: var(--geo-main);" role="status"></div>
                                                  <div class="mt-2 text-muted">Стягиваем данные с NextGIS...</div>
                                               </div>`;

  try {
    const response = await fetch(`${nextgisBaseUrl}/api/resource/${vectorId}/feature/?geom=no`);
    const data = await response.json();

    if (!data || data.length === 0) {
      if(attrContainer) attrContainer.innerHTML = `<div class="alert alert-warning mt-3">Слой пуст или данных нет.</div>`;
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
    if(attrContainer) attrContainer.innerHTML = tableHTML;
  } catch(err) {
    if(attrContainer) attrContainer.innerHTML = `<div class="alert alert-danger mt-3">Ошибка загрузки данных.</div>`;
  }
}

// ==========================================
// БЛОК: СИНХРОНИЗАЦИЯ МАСШТАБА (QGIS STYLE)
// ==========================================
const scaleSelect = document.getElementById('scaleSelect');

if (scaleSelect) {
  // 1. Когда геолог выбирает масштаб из списка -> меняем зум карты
  scaleSelect.addEventListener('change', (e) => {
    map.setZoom(parseInt(e.target.value));
  });

  // 2. Когда геолог крутит колесико мыши -> меняем цифру в списке
  map.on('zoomend', () => {
    const currentZoom = map.getZoom();
    
    // Ищем в нашем списке масштабов ближайший к текущему зуму
    let closestOption = scaleSelect.options[0];
    let minDiff = Infinity;
    
    Array.from(scaleSelect.options).forEach(opt => {
      const diff = Math.abs(parseInt(opt.value) - currentZoom);
      if (diff < minDiff) {
        minDiff = diff;
        closestOption = opt;
      }
    });
    
    scaleSelect.value = closestOption.value;
  });

  // Устанавливаем правильное значение при первой загрузке
  map.fire('zoomend');
}