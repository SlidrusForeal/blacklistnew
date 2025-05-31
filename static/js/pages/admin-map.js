const MAP_CONFIG = {
  WORLD_SIZE: 3000, // Default world size, can be adjusted
  UPDATE_INTERVAL: 60000, // Interval for full data refresh (e.g., 60 seconds)
  INITIAL_ZOOM: 0,
  HEATMAP_CONFIG: {
    radius: 20,
    blur: 15,
    maxZoom: 4, // Heatmap might be too intense at high zoom
    gradient: { 0.4: 'blue', 0.65: 'lime', 0.9: 'red' }
  }
};

class PlayerMap {
  constructor(supabaseClient) {
    this.supabase = supabaseClient;
    this.markers = new Map(); // uuid -> { marker, data }
    this.heatLayer = null;
    this.gridLayer = null;
    this.heatmapEnabled = true;
    this.gridEnabled = true;
    this.playerData = new Map(); // uuid -> player data from API
    
    this.initMap();
    this.initControls();
    this.fetchInitialData(); // Fetch initial data, then subscribe to realtime
  }

  initMap() {
    const bounds = [[-MAP_CONFIG.WORLD_SIZE, -MAP_CONFIG.WORLD_SIZE], [MAP_CONFIG.WORLD_SIZE, MAP_CONFIG.WORLD_SIZE]];
    
    this.map = L.map('activityMap', {
      crs: L.CRS.Simple,
      zoomControl: true,
      attributionControl: false, // No attribution needed for simple CRS
      minZoom: -4, // Adjusted zoom levels
      maxZoom: 5
    });

    this.map.fitBounds(bounds);
    this.map.setMaxBounds(bounds); // Prevent panning outside world
    this.map.setView([0, 0], MAP_CONFIG.INITIAL_ZOOM);
    
    if (this.gridEnabled) this.drawChunkGrid();
  }

  initControls() {
    document.getElementById('toggleHeatmap').addEventListener('click', () => this.toggleHeatmap());
    document.getElementById('toggleGrid').addEventListener('click', () => this.toggleGrid());
    document.getElementById('centerMap').addEventListener('click', () => this.centerMap());
  }

  drawChunkGrid() {
    if (this.gridLayer) this.map.removeLayer(this.gridLayer);
    this.gridLayer = L.layerGroup();
    const step = 16; // Chunk size
    const style = { color: '#444', weight: 1, opacity: 0.5 };

    for (let i = -MAP_CONFIG.WORLD_SIZE; i <= MAP_CONFIG.WORLD_SIZE; i += step) {
      L.polyline([[i, -MAP_CONFIG.WORLD_SIZE], [i, MAP_CONFIG.WORLD_SIZE]], style).addTo(this.gridLayer);
      L.polyline([[-MAP_CONFIG.WORLD_SIZE, i], [MAP_CONFIG.WORLD_SIZE, i]], style).addTo(this.gridLayer);
    }
    this.gridLayer.addTo(this.map);
  }

  toggleGrid() {
    this.gridEnabled = !this.gridEnabled;
    document.getElementById('toggleGrid').textContent = `Сетка чанков (${this.gridEnabled ? 'Вкл' : 'Выкл'})`;
    if (this.gridEnabled) {
      if (!this.gridLayer) this.drawChunkGrid();
      else this.gridLayer.addTo(this.map);
    } else {
      if (this.gridLayer) this.map.removeLayer(this.gridLayer);
    }
  }

  toggleHeatmap() {
    this.heatmapEnabled = !this.heatmapEnabled;
    document.getElementById('toggleHeatmap').textContent = `Тепловая карта (${this.heatmapEnabled ? 'Вкл' : 'Выкл'})`;
    if (this.heatmapEnabled && this.heatLayer) {
      this.heatLayer.addTo(this.map);
    } else if (this.heatLayer) {
      this.map.removeLayer(this.heatLayer);
    }
    // If enabling and no data yet, it will be added when data arrives
  }

  centerMap() {
    this.map.setView([0, 0], MAP_CONFIG.INITIAL_ZOOM);
  }

  updatePlayerList(currentPlayersData) {
    const playerListElement = document.getElementById('player-list');
    const noPlayersMessage = document.getElementById('no-players-message');
    playerListElement.innerHTML = ''; // Clear existing

    const sortedPlayers = Array.from(currentPlayersData.values()).sort((a, b) => {
        // Sort by nickname, then by UUID if nickname is unknown or same
        const nickA = a.nickname || 'zzz'; // Put unknown last
        const nickB = b.nickname || 'zzz';
        if (nickA.toLowerCase() < nickB.toLowerCase()) return -1;
        if (nickA.toLowerCase() > nickB.toLowerCase()) return 1;
        return (a.uuid || '').localeCompare(b.uuid || '');
    });

    if (sortedPlayers.length === 0) {
        noPlayersMessage.style.display = 'block';
        playerListElement.appendChild(noPlayersMessage);
        return;
    }
    
    noPlayersMessage.style.display = 'none';

    sortedPlayers.forEach(player => {
      const li = document.createElement('li');
      li.className = 'player-item';
      li.dataset.uuid = player.uuid;
      li.innerHTML = `
        <img src="https://minotar.net/avatar/${player.uuid}/24" alt="Avatar" class="player-avatar" loading="lazy">
        <div class="player-info">
          <div class="player-nickname">${player.nickname || 'Unknown'}</div>
          <div class="player-coords">X: ${Math.round(player.x)}, Z: ${Math.round(player.z)}</div>
        </div>
      `;
      li.addEventListener('click', () => {
        const pos = [player.x, player.z];
        this.map.setView(pos, 2);
        if (this.markers.has(player.uuid)) {
          this.markers.get(player.uuid).marker.openPopup();
        }
      });
      playerListElement.appendChild(li);
    });
  }

  async fetchInitialData() {
    try {
      const { data, error } = await this.supabase
        .from('player_locations')
        .select('*')
        .gte('last_seen', new Date(Date.now() - 3600000).toISOString());

      if (error) throw error;

      this.updateMarkers(data);
      this.setupRealtimeSubscription();

      // Set up periodic full refresh
      setInterval(() => this.fetchInitialData(), MAP_CONFIG.UPDATE_INTERVAL);
    } catch (error) {
      console.error('Error fetching initial data:', error);
      showToast('Ошибка при загрузке данных карты', 'error');
    }
  }

  setupRealtimeSubscription() {
    this.supabase
      .channel('player_locations')
      .on('postgres_changes', {
        event: '*',
        schema: 'public',
        table: 'player_locations'
      }, payload => {
        switch (payload.eventType) {
          case 'INSERT':
          case 'UPDATE':
            this.updateMarkers([payload.new]);
            break;
          case 'DELETE':
            this.removeMarker(payload.old.uuid);
            break;
        }
      })
      .subscribe();
  }

  updateMarkers(players) {
    const currentTime = Date.now();
    const oneHourAgo = currentTime - 3600000; // 1 hour in milliseconds

    players.forEach(player => {
      const lastSeen = new Date(player.last_seen).getTime();
      if (lastSeen < oneHourAgo) {
        this.removeMarker(player.uuid);
        return;
      }

      const pos = [player.x, player.z];
      let marker;

      if (this.markers.has(player.uuid)) {
        marker = this.markers.get(player.uuid).marker;
        marker.setLatLng(pos);
        marker.getPopup().setContent(this.createPopupContent(player));
      } else {
        marker = L.marker(pos)
          .bindPopup(this.createPopupContent(player))
          .addTo(this.map);
      }

      this.markers.set(player.uuid, { marker, data: player });
    });

    // Update heatmap
    if (this.heatmapEnabled) {
      this.updateHeatmap();
    }

    // Update player list
    this.updatePlayerList(new Map(Array.from(this.markers.entries()).map(([uuid, { data }]) => [uuid, data])));
  }

  removeMarker(uuid) {
    if (this.markers.has(uuid)) {
      this.markers.get(uuid).marker.remove();
      this.markers.delete(uuid);
      this.updateHeatmap();
      this.updatePlayerList(new Map(Array.from(this.markers.entries()).map(([uuid, { data }]) => [uuid, data])));
    }
  }

  updateHeatmap() {
    const points = Array.from(this.markers.values()).map(({ data }) => [data.x, data.z, 1]);
    
    if (this.heatLayer) {
      this.map.removeLayer(this.heatLayer);
    }

    this.heatLayer = L.heatLayer(points, MAP_CONFIG.HEATMAP_CONFIG);
    
    if (this.heatmapEnabled) {
      this.heatLayer.addTo(this.map);
    }
  }

  createPopupContent(player) {
    return `
      <div class="player-popup">
        <img src="https://minotar.net/avatar/${player.uuid}/64" alt="Avatar" style="width:64px;height:64px;display:block;margin:0 auto;">
        <h3>${player.nickname || 'Unknown'}</h3>
        <p>UUID: ${player.uuid}</p>
        <p>Координаты: X: ${Math.round(player.x)}, Z: ${Math.round(player.z)}</p>
        <p>Последняя активность: ${new Date(player.last_seen).toLocaleString()}</p>
      </div>
    `;
  }
}

// Initialize map when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
  // Ensure Supabase client is initialized
  if (!window.supabaseInstance) {
    console.error('Supabase client not initialized');
    return;
  }
  
  // Create map instance
  const map = new PlayerMap(window.supabaseInstance);
}); 