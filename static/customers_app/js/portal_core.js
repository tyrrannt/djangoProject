/**
 * КОРПОРАТИВНЫЙ ПОРТАЛ — Ядро клиентских скриптов (Portal Core)
 * Управление сайдбаром, WebSockets, онлайн-пользователями, личными сообщениями и безопасностью.
 */

(function () {
    'use strict';

    // =========================================================================
    // 1. Безопасное снятие Loading Overlay
    // =========================================================================
    function dismissLoadingOverlay() {
        var overlay = document.getElementById('LoadingOverlayApi');
        if (overlay) {
            overlay.style.display = 'none';
        }
        if (document.body) {
            document.body.classList.remove('loading-overlay-showing');
        }
    }

    // Гарантированное снятие спиннера после загрузки или по таймауту безопасности
    window.addEventListener('load', function () {
        setTimeout(dismissLoadingOverlay, 150);
    });
    setTimeout(dismissLoadingOverlay, 1200);

    // =========================================================================
    // 2. Инициализация и сохранение позиции NanoScroller в боковом меню
    // =========================================================================
    function initSidebarNanoScroll() {
        var nanoContainer = document.querySelector('#sidebar-left .nano');
        if (!nanoContainer) return;

        var sidebarLeft = document.getElementById('sidebar-left');
        if (sidebarLeft) {
            var windowHeight = window.innerHeight;
            var headerEl = document.querySelector('header.header');
            var sidebarHeaderEl = document.querySelector('.sidebar-header');
            var headerHeight = headerEl ? headerEl.offsetHeight : 60;
            var sidebarHeaderHeight = sidebarHeaderEl ? sidebarHeaderEl.offsetHeight : 40;
            var nanoHeight = windowHeight - headerHeight - sidebarHeaderHeight;
            nanoContainer.style.height = Math.max(nanoHeight, 200) + 'px';
        }

        if (typeof jQuery !== 'undefined' && jQuery.fn.nanoScroller) {
            var initialPosition = 0;
            if (typeof localStorage !== 'undefined') {
                var savedPos = localStorage.getItem('sidebar-left-position');
                if (savedPos !== null) {
                    initialPosition = parseInt(savedPos, 10) || 0;
                }
            }

            try {
                jQuery(nanoContainer).nanoScroller({ destroy: true });
            } catch (e) {
                // Игнорируем если не был инициализирован
            }

            jQuery(nanoContainer).nanoScroller({
                scrollTop: initialPosition,
                alwaysVisible: true,
                preventPageScrolling: true
            });
        }
    }

    // Сохранение скролла при прокрутке
    document.addEventListener('DOMContentLoaded', function () {
        var sidebarNanoContent = document.querySelector('#sidebar-left .nano-content');
        if (sidebarNanoContent && typeof localStorage !== 'undefined') {
            sidebarNanoContent.addEventListener('scroll', function () {
                localStorage.setItem('sidebar-left-position', sidebarNanoContent.scrollTop);
            });
            var initialPos = localStorage.getItem('sidebar-left-position');
            if (initialPos !== null) {
                sidebarNanoContent.scrollTop = parseInt(initialPos, 10) || 0;
            }
        }
        initSidebarNanoScroll();
    });

    var resizeNanoTimer;
    window.addEventListener('resize', function () {
        clearTimeout(resizeNanoTimer);
        resizeNanoTimer = setTimeout(initSidebarNanoScroll, 200);
    });

    // =========================================================================
    // 3. Таймер действия QR-кода
    // =========================================================================
    document.addEventListener('DOMContentLoaded', function () {
        var countdownEl = document.getElementById('countdown');
        var qrCodeImg = document.getElementById('qr-code-image');
        var expiredMsg = document.getElementById('expired-message');
        var qrCodeMsg = document.getElementById('qr-code-message');

        if (!countdownEl || !qrCodeImg) return;

        var timeLeft = 30;
        function updateQrCountdown() {
            if (countdownEl) countdownEl.textContent = timeLeft + ' сек';
            timeLeft--;

            if (timeLeft < 0) {
                clearInterval(qrInterval);
                if (countdownEl) countdownEl.style.display = 'none';
                if (qrCodeImg) qrCodeImg.style.display = 'none';
                if (qrCodeMsg) qrCodeMsg.style.display = 'none';
                if (expiredMsg) expiredMsg.style.display = 'block';
            }
        }

        var qrInterval = setInterval(updateQrCountdown, 1000);
    });

    // =========================================================================
    // 4. WebSocket: Онлайн-пользователи и Личные сообщения
    // =========================================================================
    function showPrivateMessageToast(from, text) {
        var toastArea = document.getElementById('toastAreaCenter');
        if (!toastArea) return;

        var toastId = 'toast-' + Date.now();
        var toastHtml = [
            '<div id="' + toastId + '" class="toast toast-soft fade" role="alert" aria-live="assertive" aria-atomic="true">',
            '  <div class="toast-header">',
            '    <strong class="me-auto"><i class="fas fa-comment text-primary me-1"></i>' + from + '</strong>',
            '    <small class="text-muted">сообщение</small>',
            '    <button type="button" class="btn-close ms-2 mb-1" data-bs-dismiss="toast" aria-label="Закрыть"></button>',
            '  </div>',
            '  <div class="toast-body">' + text + '</div>',
            '</div>'
        ].join('');

        toastArea.insertAdjacentHTML('beforeend', toastHtml);
        var toastEl = document.getElementById(toastId);
        if (toastEl && typeof bootstrap !== 'undefined' && bootstrap.Toast) {
            var bsToast = new bootstrap.Toast(toastEl, { autohide: false, animation: true });
            bsToast.show();
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        var modalEl = document.getElementById('sendMessageModal');
        var selectedUserId = null;
        var bsModal = null;

        if (modalEl && typeof bootstrap !== 'undefined' && bootstrap.Modal) {
            bsModal = new bootstrap.Modal(modalEl);
        }

        window.openModal = function (username, userId) {
            selectedUserId = userId;
            var label = document.getElementById('sendMessageLabel');
            var text = document.getElementById('modal-text');
            if (label) label.textContent = 'Сообщение для: ' + username;
            if (text) text.value = '';
            if (bsModal) bsModal.show();
        };

        var sendBtn = document.getElementById('modal-send');
        if (sendBtn) {
            sendBtn.onclick = function () {
                var textEl = document.getElementById('modal-text');
                var msg = textEl ? textEl.value.trim() : '';
                if (msg && selectedUserId && window.private_socket && window.private_socket.readyState === WebSocket.OPEN) {
                    window.private_socket.send(JSON.stringify({
                        type: 'private_message',
                        to: selectedUserId,
                        message: msg
                    }));
                }
                if (bsModal) bsModal.hide();
            };
        }

        // Подключение WebSocket с мягким восстановлением
        var wsProtocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
        var host = window.location.host;

        function connectOnlineUsers() {
            var url = wsProtocol + host + '/ws/online_users/';
            var onlineSocket;
            try {
                onlineSocket = new WebSocket(url);
            } catch (err) {
                console.warn('WebSocket [online_users] creation failed:', err);
                setTimeout(connectOnlineUsers, 5000);
                return;
            }

            onlineSocket.onopen = function () {
                console.info('WebSocket [online_users] connected via', wsProtocol);
            };

            onlineSocket.onmessage = function (event) {
                try {
                    var data = JSON.parse(event.data);
                    if (data.type === 'online_users') {
                        var usersList = document.getElementById('online-users');
                        if (!usersList) return;
                        usersList.innerHTML = '';
                        if (!data.users || data.users.length === 0) {
                            usersList.innerHTML = '<li class="text-muted fst-italic">Нет активных пользователей</li>';
                            return;
                        }
                        data.users.forEach(function (user) {
                            var username = user[0];
                            var userId = user[1];
                            var li = document.createElement('li');
                            var link = document.createElement('a');
                            link.href = '#';
                            link.className = 'd-block py-1 text-decoration-none online-user-link';
                            link.title = 'Двойной клик для отправки сообщения';
                            link.innerHTML = '<i class="fas fa-circle text-success me-2" style="font-size: 8px;"></i><span>' + username + '</span>';
                            link.addEventListener('dblclick', function (e) {
                                e.preventDefault();
                                window.openModal(username, userId);
                            });
                            li.appendChild(link);
                            usersList.appendChild(li);
                        });
                    }
                } catch (e) {
                    console.debug('Online users WS parse error:', e);
                }
            };

            onlineSocket.onerror = function (error) {
                console.warn('WebSocket [online_users] error on ' + url + ':', error);
            };

            onlineSocket.onclose = function (event) {
                console.info('WebSocket [online_users] closed (code: ' + event.code + '). Reconnecting in 5s...');
                setTimeout(connectOnlineUsers, 5000);
            };
        }

        function connectPrivateMessages() {
            var url = wsProtocol + host + '/ws/private/';
            try {
                window.private_socket = new WebSocket(url);
            } catch (err) {
                console.warn('WebSocket [private_socket] creation failed:', err);
                setTimeout(connectPrivateMessages, 5000);
                return;
            }

            window.private_socket.onopen = function () {
                console.info('WebSocket [private_messages] connected via', wsProtocol);
            };

            window.private_socket.onmessage = function (event) {
                try {
                    var data = JSON.parse(event.data);
                    if (data.type === 'private_message') {
                        showPrivateMessageToast(data.from_name || 'Пользователь', data.message || '');
                    }
                } catch (e) {
                    console.debug('Private message WS parse error:', e);
                }
            };

            window.private_socket.onerror = function (error) {
                console.warn('WebSocket [private_messages] error on ' + url + ':', error);
            };

            window.private_socket.onclose = function (event) {
                console.info('WebSocket [private_messages] closed (code: ' + event.code + '). Reconnecting in 5s...');
                setTimeout(connectPrivateMessages, 5000);
            };
        }

        connectOnlineUsers();
        connectPrivateMessages();
    });

    // =========================================================================
    // 5. Таймер неактивности пользователя (Auto-Lock Screen)
    // =========================================================================
    function initInactivityTimer(lockUrl) {
        var timer;
        var timeoutMs = 3600000; // 1 час неактивности

        function lockScreen() {
            if (lockUrl) {
                window.location.href = lockUrl;
            }
        }

        function resetTimer() {
            clearTimeout(timer);
            timer = setTimeout(lockScreen, timeoutMs);
        }

        var events = ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart'];
        events.forEach(function (eventName) {
            document.addEventListener(eventName, resetTimer, true);
        });

        resetTimer();
    }

    window.initPortalInactivityTimer = initInactivityTimer;

})();
