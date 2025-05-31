function createConfetti() {
    const colors = ['#ff0000', '#ff4444', '#ff6666', '#ff8888'];
    const container = document.querySelector('.blacklist-entries');
    
    if (!container) return;

    function createConfettiPiece() {
        const confetti = document.createElement('div');
        confetti.className = 'confetti';
        confetti.style.left = Math.random() * 100 + 'vw';
        confetti.style.backgroundColor = colors[Math.floor(Math.random() * colors.length)];
        confetti.style.width = (Math.random() * 10 + 5) + 'px';
        confetti.style.height = (Math.random() * 10 + 5) + 'px';
        document.body.appendChild(confetti);

        setTimeout(() => {
            confetti.remove();
        }, 3000);
    }

    // Create initial confetti
    for (let i = 0; i < 50; i++) {
        setTimeout(() => {
            createConfettiPiece();
        }, i * 100);
    }

    // Continue creating confetti periodically
    setInterval(() => {
        createConfettiPiece();
    }, 200);
}

// Run confetti when the page loads
document.addEventListener('DOMContentLoaded', createConfetti); 