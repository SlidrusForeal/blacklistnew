document.addEventListener('DOMContentLoaded', function() {
    const canvas = document.getElementById('confettiCanvas');
    if(canvas){
        canvas.style.display = 'block';
        const confetti = new ConfettiGenerator({ 
            target: 'confettiCanvas', 
            clock: 25,
            duration: 2000
        });
        confetti.render();
        setTimeout(() => { canvas.style.display = 'none'; }, 3000);
    }
}); 