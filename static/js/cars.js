document.addEventListener("DOMContentLoaded", () => {
    const cars = document.querySelectorAll(".tron-car");

    cars.forEach(car => {
        moveCar(car);
    });

    function moveCar(car) {
        const screenW = window.innerWidth;
        const screenH = window.innerHeight;

        // Start zufällig irgendwo
        let x = Math.random() * screenW;
        let y = Math.random() * screenH;
        let angle = 0;

        // zufällige Geschwindigkeit
        const speed = 1 + Math.random() * 3;

        function pickNewTarget() {
            return {
                x: Math.random() * screenW,
                y: Math.random() * screenH
            };
        }

        let target = pickNewTarget();

        function animate() {
            const dx = target.x - x;
            const dy = target.y - y;
            const dist = Math.sqrt(dx * dx + dy * dy);

            if (dist < 10) {
                target = pickNewTarget();
            } else {
                x += (dx / dist) * speed;
                y += (dy / dist) * speed;
                angle = Math.atan2(dy, dx) * (180 / Math.PI);
            }

            car.style.transform = `translate(${x}px, ${y}px) rotate(${angle}deg)`;

            requestAnimationFrame(animate);
        }

        animate();
    }
});