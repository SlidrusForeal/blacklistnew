// static/js/filter-list.js

const imgs = document.querySelectorAll('img[data-src]');
const observer = new IntersectionObserver(entries => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      const img = entry.target;
      img.src = img.dataset.src;
      img.classList.remove('skeleton');
      observer.unobserve(img);
    }
  });
});
imgs.forEach(img => observer.observe(img));

document.addEventListener('DOMContentLoaded', () => {
  const inp = document.getElementById("search-input");
  if (!inp) return;
  inp.addEventListener("input", function() {
    const term = this.value.toLowerCase();
    document.querySelectorAll("#blacklist li").forEach(li => {
      li.style.display = li.textContent.toLowerCase().includes(term)
        ? ""
        : "none";
    });
  });
});
