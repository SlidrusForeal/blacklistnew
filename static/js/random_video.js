// Enhanced random video player
(() => {
  'use strict';

  // Configuration
  const CONFIG = {
    videos: [
      {
        src: 'trololo.mp4',
        title: 'Trololo',
        poster: '/static/images/trololo-poster.jpg'
      },
      {
        src: 'rickroll.mp4',
        title: 'Never Gonna Give You Up',
        poster: '/static/images/rickroll-poster.jpg'
      },
      {
        src: 'crocodildo.mp4',
        title: 'Crocodildo',
        poster: '/static/images/crocodildo-poster.jpg'
      }
    ],
    basePath: '/static/videos/',
    autoplay: true,
    preload: 'metadata',
    controls: true,
    playbackRates: [0.5, 1, 1.5, 2]
  };

  // Utility functions
  const getRandomItem = (array) => array[Math.floor(Math.random() * array.length)];

  const formatTime = (seconds) => {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    return [
      h > 0 ? h : null,
      h > 0 ? m.toString().padStart(2, '0') : m,
      s.toString().padStart(2, '0')
    ].filter(Boolean).join(':');
  };

  // Video player setup
  const setupVideoPlayer = () => {
    const videoContainer = document.getElementById('video-container');
    const video = document.getElementById('random-video');
    if (!video) return;

    // Select random video
    const selectedVideo = getRandomItem(CONFIG.videos);
    
    // Setup video attributes
    video.src = CONFIG.basePath + selectedVideo.src;
    video.title = selectedVideo.title;
    if (selectedVideo.poster) {
      video.poster = selectedVideo.poster;
    }
    video.controls = CONFIG.controls;
    video.preload = CONFIG.preload;
    if (CONFIG.autoplay) {
      video.autoplay = true;
      video.muted = true;
    }

    // Create custom controls if needed
    if (videoContainer && CONFIG.customControls) {
      const controls = document.createElement('div');
      controls.className = 'video-controls';
      controls.innerHTML = `
        <button class="play-pause" aria-label="Play">▶</button>
        <div class="progress-bar">
          <div class="progress"></div>
          <div class="buffer"></div>
        </div>
        <span class="time">0:00 / 0:00</span>
        <button class="mute" aria-label="Mute">🔊</button>
        <select class="playback-rate" aria-label="Playback Speed">
          ${CONFIG.playbackRates.map(rate => 
            `<option value="${rate}"${rate === 1 ? ' selected' : ''}>${rate}x</option>`
          ).join('')}
        </select>
        <button class="fullscreen" aria-label="Fullscreen">⛶</button>
      `;
      videoContainer.appendChild(controls);

      // Setup custom controls functionality
      setupCustomControls(video, controls);
    }

    // Error handling
    video.addEventListener('error', (e) => {
      console.error('Video error:', e);
      const errorMessage = document.createElement('div');
      errorMessage.className = 'video-error';
      errorMessage.innerHTML = `
        <p>Sorry, there was an error loading the video.</p>
        <button onclick="location.reload()">Try Another Video</button>
      `;
      video.parentNode.insertBefore(errorMessage, video);
      video.style.display = 'none';
    });

    // Loading indicator
    const loadingSpinner = document.createElement('div');
    loadingSpinner.className = 'video-loading';
    loadingSpinner.innerHTML = '<div class="spinner"></div>';
    video.parentNode.insertBefore(loadingSpinner, video);

    video.addEventListener('canplay', () => {
      loadingSpinner.style.display = 'none';
    });

    video.addEventListener('waiting', () => {
      loadingSpinner.style.display = 'flex';
    });

    video.addEventListener('playing', () => {
      loadingSpinner.style.display = 'none';
    });

    // Load video
    video.load();
  };

  // Custom controls setup
  const setupCustomControls = (video, controls) => {
    const playPauseBtn = controls.querySelector('.play-pause');
    const progressBar = controls.querySelector('.progress-bar');
    const progress = controls.querySelector('.progress');
    const buffer = controls.querySelector('.buffer');
    const timeDisplay = controls.querySelector('.time');
    const muteBtn = controls.querySelector('.mute');
    const playbackSelect = controls.querySelector('.playback-rate');
    const fullscreenBtn = controls.querySelector('.fullscreen');

    // Play/Pause
    playPauseBtn.addEventListener('click', () => {
      if (video.paused) {
        video.play();
        playPauseBtn.textContent = '⏸';
        playPauseBtn.setAttribute('aria-label', 'Pause');
      } else {
        video.pause();
        playPauseBtn.textContent = '▶';
        playPauseBtn.setAttribute('aria-label', 'Play');
      }
    });

    // Progress bar
    video.addEventListener('timeupdate', () => {
      const percent = (video.currentTime / video.duration) * 100;
      progress.style.width = `${percent}%`;
      timeDisplay.textContent = `${formatTime(video.currentTime)} / ${formatTime(video.duration)}`;
    });

    video.addEventListener('progress', () => {
      if (video.buffered.length > 0) {
        const bufferedEnd = video.buffered.end(video.buffered.length - 1);
        const percent = (bufferedEnd / video.duration) * 100;
        buffer.style.width = `${percent}%`;
      }
    });

    progressBar.addEventListener('click', (e) => {
      const rect = progressBar.getBoundingClientRect();
      const percent = (e.clientX - rect.left) / rect.width;
      video.currentTime = video.duration * percent;
    });

    // Mute
    muteBtn.addEventListener('click', () => {
      video.muted = !video.muted;
      muteBtn.textContent = video.muted ? '🔇' : '🔊';
      muteBtn.setAttribute('aria-label', video.muted ? 'Unmute' : 'Mute');
    });

    // Playback rate
    playbackSelect.addEventListener('change', () => {
      video.playbackRate = parseFloat(playbackSelect.value);
    });

    // Fullscreen
    fullscreenBtn.addEventListener('click', () => {
      if (document.fullscreenElement) {
        document.exitFullscreen();
      } else {
        video.requestFullscreen();
      }
    });

    // Keyboard controls
    document.addEventListener('keydown', (e) => {
      if (document.activeElement.tagName === 'INPUT') return;

      switch (e.key.toLowerCase()) {
        case ' ':
        case 'k':
          e.preventDefault();
          playPauseBtn.click();
          break;
        case 'm':
          e.preventDefault();
          muteBtn.click();
          break;
        case 'f':
          e.preventDefault();
          fullscreenBtn.click();
          break;
        case 'arrowleft':
          e.preventDefault();
          video.currentTime = Math.max(0, video.currentTime - 5);
          break;
        case 'arrowright':
          e.preventDefault();
          video.currentTime = Math.min(video.duration, video.currentTime + 5);
          break;
      }
    });
  };

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupVideoPlayer);
  } else {
    setupVideoPlayer();
  }
})();
