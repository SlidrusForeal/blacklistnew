document.addEventListener('DOMContentLoaded', () => {
  const videos = [
    'trololo.mp4',
    'rickroll.mp4',
    'crocodildo.mp4'
  ];
  const choice = videos[Math.floor(Math.random() * videos.length)];
  const videoEl = document.getElementById('random-video');
  videoEl.src = `/static/videos/${choice}`;
  videoEl.load();
});
