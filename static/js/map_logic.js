/**
 * ГЛАВНЫЙ СКРИПТ КАРТЫ (ГИС Забайкальского края)
 */

const nextgisBaseUrl = ""; // Адрес сервера (если нужен)

// ==========================================
// БЛОК 1: ИНИЦИАЛИЗАЦИЯ КАРТЫ
// ==========================================
const map = L.map("map", { zoomControl: false, minZoom: 3, maxZoom: 18 }).setView([52.03, 117.5], 6);
L.control.zoom({ position: "bottomleft" }).addTo(map);
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
// БЛОК 2: АРХИТЕКТУРА ИНТЕРФЕЙСА
// ==========================================
const sidebar = document.getElementById("layersSidebar");
const btnCollapse = document.getElementById("layersSidebarCollapse");
const iconToggle = document.getElementById("layerToggleIcon");

if (window.innerWidth <= 768) {
  if (sidebar) sidebar.classList.add("collapsed");
  if (iconToggle) iconToggle.className = "bi bi-chevron-right";
}

if (btnCollapse) {
  btnCollapse.addEventListener("click", () => {
    sidebar.classList.toggle("collapsed");
    iconToggle.className = sidebar.classList.contains("collapsed") ? "bi bi-chevron-right" : "bi bi-chevron-left";
    setTimeout(() => map.invalidateSize(), 300);
  });
}

map.on('click', () => {
  if (window.innerWidth <= 768 && sidebar && !sidebar.classList.contains("collapsed")) {
    sidebar.classList.add("collapsed");
    if (iconToggle) iconToggle.className = "bi bi-chevron-right";
  }
});

function isFolderChecked(chk) {
  const folder = chk.closest('.collapse');
  if (!folder) return true;
  const container = folder.parentElement;
  const masterCheck = container.querySelector('.folder-master-checkbox');
  return masterCheck ? masterCheck.checked : true;
}

// ==========================================
// БЛОК 3: ДИНАМИЧЕСКИЙ ДВИЖОК СЛОЕВ
// ==========================================
let dynamicQueryQueue = [];

function showForbiddenToast(layerName) {
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

async function initDynamicLayers() {
    try {
        const response = await fetch('/api/layers_config');
        if (!response.ok) throw new Error('Ошибка загрузки конфига');
        const config = await response.json();
        
        const container = document.getElementById('layersAccordion');
        if (!container) return;
        container.innerHTML = ''; 

        let folderIndex = 0;

        for (const [categoryName, subcategories] of Object.entries(config)) {
            folderIndex++;
            const folderId = `dyn_folder_${folderIndex}`;
            
            let categoryHtmlContent = "";
            let hasAnyLayerInCategory = false; 

            for (const [subName, layers] of Object.entries(subcategories)) {
                let subcategoryHtmlContent = "";
                let hasAnyLayerInSub = false; 

                for (const [layerName, ids] of Object.entries(layers)) {
                    const vectorId = ids[0];
                    const rasterId = ids[1] || ids[0];
                    const chkId = `chk_${rasterId}`;
                    
                    // Безопасное чтение прав с бэкенда
                    let allowed = [];
                    let isAllAllowed = false;
                    
                    if (typeof userAllowedLayers !== 'undefined') {
                        if (userAllowedLayers === "*") {
                            isAllAllowed = true;
                        } else if (Array.isArray(userAllowedLayers)) {
                            allowed = userAllowedLayers;
                        } else if (typeof userAllowedLayers === 'string') {
                            try { allowed = JSON.parse(userAllowedLayers); } catch(e) {}
                        }
                    }

                    const isAllowed = isAllAllowed || allowed.includes(rasterId) || allowed.includes(vectorId);

                    if (isAllowed) {
                        hasAnyLayerInSub = true;
                        hasAnyLayerInCategory = true;
                        
                        // Гибриды только для реальных точек (ИСПРАВЛЕНО)
                        const isPointLayer = layerName.includes('Населённые пункты') || 
                                             layerName.includes('Месторождения') || 
                                             layerName.includes('Рудопроявления') || 
                                             layerName.includes('Пункты минерализации');
                                             
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

                if (hasAnyLayerInSub) {
                    categoryHtmlContent += `
                    <div class="fw-bold mt-2 mb-1 ms-2 small text-secondary d-flex align-items-center">
                        <input type="checkbox" class="form-check-input me-2 mb-0 sub-master-checkbox" style="margin-top: 0; margin-left: -15px; cursor: pointer;" title="Выбрать подгруппу">
                        ${subName}
                    </div>` + subcategoryHtmlContent;
                }
            }

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

function bindDynamicLogic() {
    document.querySelectorAll('.folder-master-checkbox').forEach(master => {
        master.addEventListener('change', (e) => {
            const folder = e.target.closest('.border').querySelector('.collapse');
            if(folder) {
                folder.querySelectorAll('.dyn-layer-chk').forEach(chk => {
                    chk.dispatchEvent(new Event('folderToggled'));
                });
            }
        });
    });

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

    document.querySelectorAll('.dyn-layer-chk').forEach(chk => {
        const rasterId = chk.getAttribute('data-raster');
        const vectorId = chk.getAttribute('data-vector');
        const layerName = chk.getAttribute('data-name');
        const isHybrid = chk.getAttribute('data-hybrid') === 'true';
        const switchZoom = 9;
        
        const tmsLayer = L.tileLayer(`${nextgisBaseUrl}/api/component/render/tile?resource=${rasterId}&nd=204&z={z}&x={x}&y={y}`, {
            transparent: true, format: 'image/png', noWrap: true, zIndex: isHybrid ? 70 : 10
        });

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
            }
        }

        function updateVisibility() {
            if (!(chk.checked && isFolderChecked(chk))) {
                if (map.hasLayer(tmsLayer)) map.removeLayer(tmsLayer);
                if (isHybrid && clusterGroup && map.hasLayer(clusterGroup)) map.removeLayer(clusterGroup);
                return;
            }
            
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
                if (!map.hasLayer(tmsLayer)) map.addLayer(tmsLayer);
            }
        }

        chk.addEventListener("change", updateVisibility);
        chk.addEventListener("folderToggled", updateVisibility);
        if (isHybrid) map.on('zoomend', updateVisibility);
    });
    
    document.querySelectorAll('.attr-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.preventDefault();
            const vid = btn.getAttribute('data-vid');
            const lname = btn.getAttribute('data-lname');
            
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
// БЛОК 4: BBOX КЛИК ПО КАРТЕ
// ==========================================
map.on('click', async function(e) {
    const point = L.CRS.EPSG3857.project(e.latlng);
    
    let activeLayers = dynamicQueryQueue.filter(layer => {
        const checkbox = document.getElementById(layer.chkId);
        return checkbox && checkbox.checked && isFolderChecked(checkbox);
    });

    if (activeLayers.length === 0) return;

    activeLayers.sort((a, b) => b.delta - a.delta);

    for (const layer of activeLayers) {
        const d = layer.delta; 
        const bbox = `${point.x - d} ${point.y - d}, ${point.x + d} ${point.y - d}, ${point.x + d} ${point.y + d}, ${point.x - d} ${point.y + d}, ${point.x - d} ${point.y - d}`;
        const wktPolygon = `POLYGON((${bbox}))`;
        const url = `${nextgisBaseUrl}/api/resource/${layer.vectorId}/feature/?intersects=${encodeURIComponent(wktPolygon)}&geom=no`;
        
        try {
            const response = await fetch(url);
            if (response.status === 403) {
                showForbiddenToast(layer.name);
                continue;
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
                break; 
            }
        } catch(err) {
            console.error(`Ошибка при запросе к слою ${layer.vectorId}:`, err);
        }
    }
});

// ==========================================
// БЛОК 5: ТАБЛИЦА АТРИБУТОВ И СИНХРОНИЗАЦИЯ МАСШТАБА
// ==========================================
const attrSidebar = document.getElementById('attributeSidebar');
const closeAttrBtn = document.getElementById('closeAttributeSidebar');
const attrContainer = document.getElementById('attributeTableContainer');

if(closeAttrBtn) {
  closeAttrBtn.addEventListener('click', () => { if(attrSidebar) attrSidebar.classList.remove('open'); });
}

async function loadAttributeTable(vectorId, layerName) {
  if(attrSidebar) attrSidebar.classList.add('open');
  if(attrContainer) attrContainer.innerHTML = `<div class="text-center mt-5">
                                                  <div class="spinner-border" style="color: var(--geo-main);" role="status"></div>
                                                  <div class="mt-2 text-muted">Стягиваем данные с сервера...</div>
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

const scaleSelect = document.getElementById('scaleSelect');
if (scaleSelect) {
  scaleSelect.addEventListener('change', (e) => {
    map.setZoom(parseInt(e.target.value));
  });

  map.on('zoomend', () => {
    const currentZoom = map.getZoom();
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
  map.fire('zoomend');
}

// --- Глобальное состояние корзины ---
let compareCart = []; 
let currentLayerId = null; // Храним ID слоя, чтобы сравнивать только однотипные объекты

// --- 1. Генерация кнопок для попапа (Leaflet) ---
// Эту функцию нужно вызывать внутри твоего bindPopup() при клике на объект
function getPopupButtonsHTML(layerId, objectId, objectName) {
    return `
        <div class="mt-3 border-top pt-2">
            <button class="btn btn-sm btn-outline-danger w-100 mb-2 fw-medium" 
                    onclick="downloadReport('solo', ${layerId}, ${objectId})">
                <i class="bi bi-file-pdf me-1"></i> Скачать PDF
            </button>
            <button class="btn btn-sm w-100 fw-medium ${isObjectInCart(objectId) ? 'btn-success' : 'btn-outline-primary'}" 
                    onclick="toggleCompareCart(${layerId}, ${objectId}, '${objectName}', this)">
                <i class="bi ${isObjectInCart(objectId) ? 'bi-check-lg' : 'bi-plus-circle'} me-1"></i> 
                ${isObjectInCart(objectId) ? 'В корзине' : 'К сравнению'}
            </button>
        </div>
    `;
}

// --- 2. Управление корзиной ---
function isObjectInCart(objectId) {
    return compareCart.some(obj => obj.id === objectId);
}

function toggleCompareCart(layerId, objectId, objectName, btnElement) {
    // Запрещаем сравнивать объекты из разных слоев (у них разные атрибуты)
    if (currentLayerId !== null && currentLayerId !== layerId && compareCart.length > 0) {
        alert("Для сравнения можно добавлять объекты только из одного слоя!");
        return;
    }

    if (isObjectInCart(objectId)) {
        // Удаляем
        compareCart = compareCart.filter(obj => obj.id !== objectId);
        btnElement.classList.replace('btn-success', 'btn-outline-primary');
        btnElement.innerHTML = '<i class="bi bi-plus-circle me-1"></i> К сравнению';
    } else {
        // Добавляляем
        currentLayerId = layerId;
        compareCart.push({ id: objectId, name: objectName });
        btnElement.classList.replace('btn-outline-primary', 'btn-success');
        btnElement.innerHTML = '<i class="bi bi-check-lg me-1"></i> В корзине';
    }
    updateCompareUI();
}

function updateCompareUI() {
    const list = document.getElementById('compareList');
    const badge = document.getElementById('compareBadge');
    const btnGenerate = document.getElementById('btnGenerateCompare');
    const btnClear = document.getElementById('btnClearCompare');
    const emptyMsg = document.getElementById('emptyCompareMsg');

    badge.innerText = compareCart.length;

    if (compareCart.length === 0) {
        currentLayerId = null;
        list.innerHTML = `<li class="list-group-item text-center text-muted py-4">Список пуст</li>`;
        btnGenerate.classList.add('d-none');
        btnClear.classList.add('d-none');
    } else {
        list.innerHTML = '';
        compareCart.forEach(obj => {
            list.innerHTML += `
                <li class="list-group-item d-flex justify-content-between align-items-center">
                    <span class="small fw-medium text-truncate" style="max-width: 85%;">${obj.name}</span>
                    <i class="bi bi-x-circle-fill text-danger text-opacity-50" style="cursor: pointer;" onclick="toggleCompareCart(${currentLayerId}, ${obj.id}, '${obj.name}', document.createElement('button'))"></i>
                </li>
            `;
        });
        
        // Разрешаем генерацию только если объектов 2 или больше
        if (compareCart.length >= 2) {
            btnGenerate.classList.remove('d-none');
        } else {
            btnGenerate.classList.add('d-none');
        }
        btnClear.classList.remove('d-none');
    }
}

function clearCompareCart() {
    compareCart = [];
    currentLayerId = null;
    updateCompareUI();
    // Закрываем все попапы Leaflet, чтобы сбросить кнопки
    if (window.map) map.closePopup(); 
}

// --- 3. Взаимодействие с API (Магия Blob) ---
async function downloadReport(mode, layerId = null, objectId = null) {
    // Определяем, что отправлять
    const targetLayerId = mode === 'solo' ? layerId : currentLayerId;
    const targetObjectIds = mode === 'solo' ? [objectId] : compareCart.map(obj => obj.id);

    // Меняем курсор и кнопку на загрузку
    document.body.style.cursor = 'wait';
    if (mode === 'compare') {
        const btn = document.getElementById('btnGenerateCompare');
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Формирование...';
        btn.disabled = true;
    }

    try {
        const response = await fetch('/api/report/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                layer_id: targetLayerId, 
                object_ids: targetObjectIds 
            })
        });

        if (!response.ok) throw new Error('Ошибка генерации PDF на сервере');

        // Читаем ответ как бинарный Blob
        const blob = await response.blob();
        
        // Создаем локальную ссылку в памяти браузера
        const downloadUrl = window.URL.createObjectURL(blob);
        
        // Создаем невидимый тег <a> и программно кликаем по нему
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = downloadUrl;
        
        // Формируем имя файла
        const dateStr = new Date().toISOString().slice(0,10);
        a.download = mode === 'solo' ? `Passport_${objectId}_${dateStr}.pdf` : `Comparison_${dateStr}.pdf`;
        
        document.body.appendChild(a);
        a.click();
        
        // Убираем за собой мусор из памяти
        window.URL.revokeObjectURL(downloadUrl);
        a.remove();

    } catch (error) {
        console.error(error);
        alert('Не удалось сгенерировать PDF. Проверьте соединение с сервером.');
    } finally {
        // Возвращаем интерфейс в норму
        document.body.style.cursor = 'default';
        if (mode === 'compare') {
            const btn = document.getElementById('btnGenerateCompare');
            btn.innerHTML = '<i class="bi bi-file-earmark-pdf-fill me-2"></i>Сгенерировать PDF-сравнение';
            btn.disabled = false;
        }
    }
}

// Объект для хранения загруженных слоев, чтобы легко ими управлять
const userCustomLayers = {};
let customLayerIdCounter = 0;

document.getElementById('localGeoInput').addEventListener('change', function(e) {
    const file = e.target.files[0];
    if (!file) return;

    const ext = file.name.split('.').pop().toLowerCase();
    const reader = new FileReader();

    // Меняем курсор на загрузку
    document.body.style.cursor = 'wait';

    // 1. Читаем Shapefile (ZIP-архив) через ArrayBuffer
    if (ext === 'zip') {
        reader.readAsArrayBuffer(file);
        reader.onload = async function(event) {
            try {
                // Библиотека shpjs сама распаковывает ZIP и выдает GeoJSON
                const geojson = await shp(event.target.result);
                addCustomLayerToMap(L.geoJSON(geojson), file.name);
            } catch (err) {
                alert('Ошибка чтения ZIP-архива. Убедитесь, что внутри лежат файлы .shp, .shx и .dbf.');
            } finally { document.body.style.cursor = 'default'; }
        }
    } 
    // 2. Читаем KML как текст
    else if (ext === 'kml') {
        reader.readAsText(file);
        reader.onload = function(event) {
            try {
                // omnivore парсит kml строку и сразу создает слой Leaflet
                const layer = omnivore.kml.parse(event.target.result);
                addCustomLayerToMap(layer, file.name);
            } catch (err) {
                alert('Ошибка чтения KML файла.');
            } finally { document.body.style.cursor = 'default'; }
        }
    } 
    // 3. Читаем нативный GeoJSON как текст
    else if (ext === 'geojson' || ext === 'json') {
        reader.readAsText(file);
        reader.onload = function(event) {
            try {
                const geojson = JSON.parse(event.target.result);
                addCustomLayerToMap(L.geoJSON(geojson), file.name);
            } catch(err) {
                alert('Ошибка формата GeoJSON.');
            } finally { document.body.style.cursor = 'default'; }
        }
    } 
    else {
        alert('Формат не поддерживается. Загрузите .zip, .kml или .geojson');
        document.body.style.cursor = 'default';
    }
    
    // Сбрасываем input, чтобы можно было загрузить этот же файл заново
    e.target.value = '';
});

// Функция добавления слоя на карту и создания UI-панели настроек
function addCustomLayerToMap(leafletLayer, fileName) {
    const layerId = 'custom_' + customLayerIdCounter++;
    
    // Применяем базовые стили по умолчанию
    leafletLayer.setStyle({
        color: '#1b578c', // Синяя обводка
        weight: 2,
        fillColor: '#f59e0b', // Оранжевая заливка
        fillOpacity: 0.5
    });
    
    leafletLayer.addTo(map); // Важно: переменная карты должна называться 'map'
    userCustomLayers[layerId] = leafletLayer;

    // Генерируем карточку управления стилями для этого слоя
    const container = document.getElementById('localLayersContainer');
    const panelHTML = `
        <div class="card border-0 shadow-sm rounded-3 bg-white p-2" id="panel_${layerId}">
            <div class="d-flex justify-content-between align-items-center mb-2 border-bottom pb-1">
                <span class="small fw-bold text-truncate" style="max-width: 70%;" title="${fileName}">${fileName}</span>
                <div>
                    <!-- Кнопки Z-index (Вверх/Вниз) -->
                    <button class="btn btn-sm btn-light py-0 px-1" onclick="moveLayer('${layerId}', 'up')" title="На передний план"><i class="bi bi-arrow-up"></i></button>
                    <button class="btn btn-sm btn-light py-0 px-1" onclick="moveLayer('${layerId}', 'down')" title="На задний план"><i class="bi bi-arrow-down"></i></button>
                    <!-- Кнопка удаления -->
                    <button class="btn btn-sm btn-outline-danger py-0 px-1 ms-1" onclick="removeLayer('${layerId}')"><i class="bi bi-trash"></i></button>
                </div>
            </div>
            
            <div class="row g-2 align-items-center">
                <div class="col-6">
                    <label class="small text-muted" style="font-size: 0.7rem;">Обводка</label>
                    <input type="color" class="form-control form-control-color w-100 p-1 h-25" value="#1b578c" onchange="updateLayerStyle('${layerId}', 'color', this.value)">
                </div>
                <div class="col-6">
                    <label class="small text-muted" style="font-size: 0.7rem;">Заливка</label>
                    <input type="color" class="form-control form-control-color w-100 p-1 h-25" value="#f59e0b" onchange="updateLayerStyle('${layerId}', 'fillColor', this.value)">
                </div>
                <div class="col-7 mt-1">
                    <label class="small text-muted" style="font-size: 0.7rem;">Прозрачность</label>
                    <input type="range" class="form-range" min="0.1" max="1" step="0.1" value="0.5" oninput="updateLayerStyle('${layerId}', 'fillOpacity', this.value)">
                </div>
                <div class="col-5 mt-1">
                    <label class="small text-muted" style="font-size: 0.7rem;">Толщина</label>
                    <input type="number" class="form-control form-control-sm" value="2" min="1" max="10" oninput="updateLayerStyle('${layerId}', 'weight', this.value)">
                </div>
            </div>
        </div>
    `;
    container.insertAdjacentHTML('afterbegin', panelHTML);
    
    // Автоматически фокусируемся на загруженном слое
    map.fitBounds(leafletLayer.getBounds());
}

// Изменение стилей слоя на лету
function updateLayerStyle(layerId, styleProp, value) {
    if (!userCustomLayers[layerId]) return;
    const layer = userCustomLayers[layerId];
    
    // Создаем объект со свойством, которое нужно обновить (например { fillOpacity: 0.8 })
    const styleObj = {};
    styleObj[styleProp] = styleProp === 'weight' || styleProp === 'fillOpacity' ? parseFloat(value) : value;
    
    layer.setStyle(styleObj);
}

// Управление Z-index (Вверх/Вниз)
function moveLayer(layerId, direction) {
    if (!userCustomLayers[layerId]) return;
    const layer = userCustomLayers[layerId];
    
    if (direction === 'up') {
        layer.bringToFront(); // Нативный метод Leaflet
    } else {
        layer.bringToBack();  // Нативный метод Leaflet
    }
}

// Удаление слоя
function removeLayer(layerId) {
    if (!userCustomLayers[layerId]) return;
    map.removeLayer(userCustomLayers[layerId]); // Удаляем с карты
    delete userCustomLayers[layerId]; // Удаляем из памяти
    document.getElementById('panel_' + layerId).remove(); // Удаляем менюшку
}