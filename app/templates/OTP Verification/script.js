        const CONFIG = {
            loadingDuration: 2000,
            errorRate: 0.15,
            vibrateMs: 15,
            successVibrate: [30, 40, 60],
            orbitDuration: 1600,
            texts: {
                idleTitle: 'Enter Access Code',
                idleSubtitle: 'A 4-digit code has been sent to your device.',
                loadingTitle: 'Verifying...',
                loadingSubtitle: 'Securely checking your credentials.',
                successTitle: 'Access Granted',
                successSubtitle: 'Welcome back. Redirecting to your vault…',
                errorTitle: 'Verification Failed',
                errorSubtitle: 'The code you entered is incorrect.'
            }
        };

        const card = document.getElementById('card');
        const title = document.getElementById('title');
        const subtitle = document.getElementById('subtitle');
        const inputStage = document.getElementById('inputStage');
        const inputs = document.querySelectorAll('.input-pill');
        const orbitLayer = document.getElementById('orbitLayer');
        const orbitRing = document.getElementById('orbitRing');
        const loadingWrap = document.getElementById('loadingWrap');
        const loadingPercent = document.getElementById('loadingPercent');
        const successWrap = document.getElementById('successWrap');
        const errorMsg = document.getElementById('errorMsg');
        const resendBtn = document.getElementById('resendBtn');
        const pointerLight = document.getElementById('pointerLight');

        let state = 'idle';
        let otp = '';
        let resetTimer = null;
        const timers = [];

        function clearAllTimers() {
            clearTimeout(resetTimer);
            timers.forEach(t => clearTimeout(t));
            timers.length = 0;
        }

        document.addEventListener('pointermove', (e) => {
            if (e.pointerType !== 'mouse') return;
            if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
            pointerLight.style.opacity = '1';
            pointerLight.style.left = `${e.clientX}px`;
            pointerLight.style.top = `${e.clientY}px`;
        });
        document.addEventListener('pointerleave', () => pointerLight.style.opacity = '0');

        function vibrate(pattern = CONFIG.vibrateMs) {
            if (navigator.vibrate) navigator.vibrate(pattern);
        }

        inputs.forEach((input, index) => {
            input.addEventListener('input', (e) => {
                if (state === 'loading' || state === 'success') return;
                if (state === 'error') resetState(true);

                const value = e.target.value.replace(/[^0-9]/g, '');
                e.target.value = value;

                if (value) {
                    vibrate();
                    e.target.classList.add('filled');
                    if (index < inputs.length - 1) {
                        inputs[index + 1].focus();
                    } else {
                        otp = Array.from(inputs).map(inp => inp.value).join('');
                        if (otp.length === 4) triggerVerify();
                    }
                } else {
                    e.target.classList.remove('filled');
                }
            });

            input.addEventListener('keydown', (e) => {
                if (e.key === 'Backspace') {
                    if (state === 'error') resetState(true);
                    if (!e.target.value && index > 0) inputs[index - 1].focus();
                }
            });

            input.addEventListener('focus', () => {
                if (state === 'error') resetState(true);
                input.select();
            });
        });

        function buildOrbit() {
            orbitRing.innerHTML = '';
            const radius = 70;
            const digits = Array.from(inputs).map(i => i.value);

            for (let i = 0; i < 4; i++) {
                const angle = (i / 4) * Math.PI * 2 - Math.PI / 2;
                const dx = Math.cos(angle) * radius;
                const dy = Math.sin(angle) * radius;

                const node = document.createElement('div');
                node.className = 'orbit-node';
                node.textContent = digits[i] || '';
                node.style.setProperty('--dx', `${dx}px`);
                node.style.setProperty('--dy', `${dy}px`);
                node.style.animationDelay = `${i * 60}ms`;
                orbitRing.appendChild(node);
            }
        }

        function playOrbit() {
            buildOrbit();
            orbitLayer.classList.add('active');
            void orbitRing.offsetWidth;
            orbitRing.classList.add('spin');
            document.querySelectorAll('.orbit-node').forEach(n => n.classList.add('node-fly'));
        }

        function spawnSplash() {
            successWrap.querySelectorAll('.confetti').forEach(c => c.remove());

            const colors = ['#10b981', '#34d399', '#6ee7b7', '#6366f1', '#a78bfa', '#fbbf24', '#f472b6', '#22d3ee'];
            const count = 24;
            const baseDist = 90;

            for (let i = 0; i < count; i++) {
                const angle = (i / count) * Math.PI * 2 + (Math.random() - 0.5) * 0.25;
                const dist = baseDist + Math.random() * 70;
                const cx = Math.cos(angle) * dist;
                const cy = Math.sin(angle) * dist;

                const dot = document.createElement('div');
                dot.className = 'confetti';
                dot.style.background = colors[i % colors.length];
                dot.style.setProperty('--cx', `${cx}px`);
                dot.style.setProperty('--cy', `${cy}px`);
                dot.style.animationDelay = `${0.1 + Math.random() * 0.15}s`;
                dot.style.boxShadow = `0 0 12px ${colors[i % colors.length]}`;

                const size = 6 + Math.random() * 10;
                dot.style.width = `${size}px`;
                dot.style.height = `${size}px`;
                if (i % 4 === 0) dot.style.borderRadius = '2px';
                else if (i % 4 === 1) dot.style.borderRadius = '50% 0 50% 0';
                else dot.style.borderRadius = '50%';

                successWrap.appendChild(dot);
            }
        }

        function triggerVerify() {
            if (state === 'loading' || state === 'success') return;
            state = 'loading';
            clearAllTimers();

            inputStage.classList.add('hidden');
            playOrbit();

            const orbitTotal = CONFIG.orbitDuration + 180;

            timers.push(setTimeout(() => {
                orbitLayer.classList.remove('active');
                orbitRing.classList.remove('spin');
                orbitRing.innerHTML = '';
                inputStage.style.display = 'none';

                title.textContent = CONFIG.texts.loadingTitle;
                subtitle.textContent = CONFIG.texts.loadingSubtitle;
                loadingWrap.classList.add('active');

                const start = performance.now();
                function tick(now) {
                    const p = Math.min((now - start) / CONFIG.loadingDuration, 1);
                    const eased = 1 - Math.pow(1 - p, 2.2);
                    loadingPercent.textContent = Math.round(eased * 100);
                    if (p < 1) requestAnimationFrame(tick);
                }
                requestAnimationFrame(tick);

                timers.push(setTimeout(() => {
                    const isSuccess = Math.random() > CONFIG.errorRate;
                    isSuccess ? handleSuccess() : handleError();
                }, CONFIG.loadingDuration));
            }, orbitTotal));
        }

        function handleSuccess() {
            state = 'success';
            vibrate(CONFIG.successVibrate);

            loadingWrap.classList.remove('active');
            spawnSplash();
            successWrap.classList.add('active');
            card.classList.add('success-tint');

            timers.push(setTimeout(() => {
                title.textContent = CONFIG.texts.successTitle;
                subtitle.textContent = CONFIG.texts.successSubtitle;
            }, 250));

            resendBtn.style.display = 'none';
        }

        function handleError() {
            state = 'error';
            vibrate([20, 60, 20]);
            loadingWrap.classList.remove('active');
            card.classList.add('shake');
            errorMsg.classList.add('show');
            title.textContent = CONFIG.texts.errorTitle;
            subtitle.textContent = CONFIG.texts.errorSubtitle;
            inputs.forEach(input => input.classList.add('error'));

            timers.push(setTimeout(() => card.classList.remove('shake'), 500));
            resetTimer = setTimeout(() => {
                if (state === 'error') resetState(false);
            }, 2000);
        }

        function resetState(immediateFocus) {
            clearAllTimers();
            state = 'idle';
            otp = '';

            card.classList.remove('shake', 'success-tint');
            errorMsg.classList.remove('show');
            title.textContent = CONFIG.texts.idleTitle;
            subtitle.textContent = CONFIG.texts.idleSubtitle;

            orbitLayer.classList.remove('active');
            orbitRing.classList.remove('spin');
            orbitRing.innerHTML = '';

            loadingWrap.classList.remove('active');
            loadingPercent.textContent = '0';

            successWrap.classList.remove('active');
            successWrap.querySelectorAll('.confetti').forEach(c => c.remove());
            successWrap.querySelectorAll('.bubble, .success-flash').forEach(el => {
                el.style.animation = 'none';
                void el.offsetWidth;
                el.style.animation = '';
            });

            inputs.forEach(input => {
                input.value = '';
                input.classList.remove('error', 'filled');
            });

            inputStage.style.display = 'flex';
            void inputStage.offsetWidth;
            inputStage.classList.remove('hidden');

            resendBtn.style.display = 'inline-block';

            if (immediateFocus !== false) inputs[0].focus();
        }

        resendBtn.addEventListener('click', () => {
            if (resendBtn.disabled) return;
            resendBtn.disabled = true;
            const original = resendBtn.innerHTML;
            resendBtn.innerHTML = `Didn't receive it? <span>Wait…</span>`;
            timers.push(setTimeout(() => {
                resendBtn.disabled = false;
                resendBtn.innerHTML = original;
                resetState(true);
            }, 2000));
        });

        window.addEventListener('load', () => {
            setTimeout(() => inputs[0].focus(), 300);
        });