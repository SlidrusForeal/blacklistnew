// static/js/ave.js
document.addEventListener('DOMContentLoaded', () => {
  function generateGradient() {
    if (!localStorage.getItem('aveGradient')) {
      const hue1 = Math.floor(Math.random() * 360);
      const hue2 = (hue1 + 150) % 360;
      localStorage.setItem(
        'aveGradient',
        `linear-gradient(135deg, hsl(${hue1},100%,50%),hsl(${hue2},100%,50%))`
      );
    }
    return localStorage.getItem('aveGradient');
  }

  const gradient = generateGradient();
  const aveEl   = document.getElementById('ave');
  const letters = document.querySelectorAll('.letter');

  letters.forEach(l => l.style.backgroundImage = gradient);

  function updatePosition(x, y) {
    const cx = innerWidth  / 2;
    const cy = innerHeight / 2;
    aveEl.style.transform = `translate(${(x-cx)*-0.05}px,${(y-cy)*-0.05}px)`;
    const ang = Math.atan2(y-cy, x-cx) * 180 / Math.PI;
    letters.forEach(l => {
      l.style.backgroundImage = `linear-gradient(${ang}deg, ${gradient})`;
    });
  }

  ['mousemove','touchmove','touchstart'].forEach(evt => {
    document.addEventListener(evt, e => {
      const {clientX:x, clientY:y} = e.touches? e.touches[0] : e;
      updatePosition(x, y);
      aveEl.classList.add('active');
    });
  });
  ['mouseleave','touchend'].forEach(evt => {
    document.addEventListener(evt, () => {
      aveEl.style.transform = 'translate(0,0)';
      aveEl.classList.remove('active');
    });
  });

  document.getElementById('year').textContent = new Date().getFullYear();
});
