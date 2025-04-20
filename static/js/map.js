(async ()=>{
  // Конфигурация зон
  const zones = [
    { name: 'Nosos', verts: [[-159,-3149],[693,-3154],[581,-2070],[-117,-2083]], color: 'red' },
    // Другие зоны можно добавить здесь
  ];

  // Инициализация карты
  const map = L.map('map').setView([0,0], 2);
  L.tileLayer('/static/vendor/tiles/{z}/{x}/{y}.png', { maxZoom:18 }).addTo(map);

  // Отрисовка зон
  zones.forEach(z=> L.polygon(
    z.verts.map(p=>[p[1],p[0]]), { color: z.color, weight:2 }
  ).addTo(map));

  // Кластеризация и heatmap
  const markers = L.markerClusterGroup();
  const heat = L.heatLayer([], { radius:25 });
  let heatOn=false;
  map.addLayer(markers);

  const players = {};

  // Переключение heatmap
  document.getElementById('toggle-heat').onclick = ()=>{
    heatOn = !heatOn;
    map.removeLayer(heatOn? markers: heat);
    map.addLayer(heatOn? heat: markers);
  };

  // Координаты курсора
  map.on('mousemove', e=>{
    document.getElementById('cursor-coords').textContent =
      `${e.latlng.lng.toFixed(2)}, ${e.latlng.lat.toFixed(2)}`;
  });

  // Фильтр по нику
  document.getElementById('search-player').oninput = ev=>{
    const q = ev.target.value.toLowerCase();
    Object.values(players).forEach(p=>{
      const has = p.name.toLowerCase().includes(q);
      has ? markers.addLayer(p.marker) : markers.removeLayer(p.marker);
    });
  };

  // Слежение
  const trackSelect = document.getElementById('track-select');
  trackSelect.onchange = ()=>{
    const uuid = trackSelect.value;
    if(uuid && players[uuid]){
      const { lat, lng } = players[uuid].history.slice(-1)[0];
      map.flyTo([lat,lng], 16);
    }
  };

  // Статистика
  const chartEl = document.getElementById('stats-chart');
  const chart = new Chart(chartEl.getContext('2d'), {
    type:'line', data:{ labels:[], datasets:[{ label:'Уникальные игроки', data:[] }] }
  });
  document.getElementById('show-chart').onclick = ()=>{
    chartEl.style.display = chartEl.style.display==='none'? 'block':'none';
  };

  // Обновление данных каждые 10 сек
  async function update(){
    const resp = await fetch('/api/locations/view');
    const data = await resp.json();
    const cutoff = Date.now()/1000 - document.getElementById('time-range').value*60;
    markers.clearLayers(); heat.setLatLngs([]);
    const seen = new Set();

    data.forEach(pt=>{
      if(!pt.timestamp) return;
      const ts = Date.parse(pt.timestamp)/1000;
      if(ts < cutoff) return;
      if(pt.world !== 'minecraft:overworld') return;
      const lat=pt.z, lng=pt.x;

      let p = players[pt.uuid];
      if(!p){
        p = players[pt.uuid] = {
          name: pt.nickname,
          history: [],
          marker: L.marker([lat,lng], {
            icon: L.divIcon({ className:'player-icon', html:`<img src="/api/avatar/${pt.uuid}"/><div>${pt.nickname}</div>` })
          }),
          trace: L.polyline([], { color:'blue' })
        };
        p.trace.addTo(map);
        markers.addLayer(p.marker);
        trackSelect.add(new Option(p.name, pt.uuid));
        L.popup({autoClose:true})
         .setLatLng([lat,lng])
         .setContent(`Игрок ${p.name} вошёл`)
         .openOn(map);
      }

      p.history.push({lat,lng,ts});
      p.trace.setLatLngs(p.history.map(h=>[h.lat,h.lng]));
      p.marker.setLatLng([lat,lng]);
      heat.addLatLng([lat,lng,0.5]);
      seen.add(pt.uuid);
    });

    // Статистика
    chart.data.labels.push(new Date().toLocaleTimeString());
    chart.data.datasets[0].data.push(seen.size);
    chart.update();
  }

  setInterval(update,10000);
  update();
})();