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

                        var countBadge = document.getElementById('online-users-count');
                        var userCount = data.users ? data.users.length : 0;
                        if (countBadge) {
                            countBadge.textContent = userCount;
                            if (userCount > 0) {
                                countBadge.classList.remove('d-none');
                            } else {
                                countBadge.classList.add('d-none');
                            }
                        }

                        if (!data.users || data.users.length === 0) {
                            usersList.innerHTML = '<li class="text-muted small fst-italic py-2 text-center">Нет активных пользователей</li>';
                            return;
                        }

                        data.users.forEach(function (user) {
                            var username = (user && user.username) ? user.username : (user ? user[0] : '');
                            var userId = (user && user.user_id) ? user.user_id : (user ? user[1] : '');
                            if (!username) return;

                            var devices = (user && user.devices && user.devices.length) ? user.devices : null;
                            if (!devices) {
                                var dType = (user && user.device_type) || (user && user[2]) || 'Компьютер / Ноутбук';
                                var dIcon = (user && user.device_icon) || (user && user[3]) || 'bx bx-laptop';
                                var dOs = (user && user.os_name) || (user && user[4]) || '';
                                var dBrowser = (user && user.browser_name) || (user && user[5]) || '';
                                devices = [{ device_type: dType, device_icon: dIcon, os_name: dOs, browser_name: dBrowser }];
                            }

                            var li = document.createElement('li');
                            li.className = 'd-flex align-items-center justify-content-between py-1 px-1 online-user-item';

                            // Левая колонка: индикатор сети, ФИО и иконки устройств
                            var userCol = document.createElement('div');
                            userCol.className = 'd-flex align-items-center text-truncate pe-1';
                            userCol.style.minWidth = '0';

                            var statusDot = document.createElement('i');
                            statusDot.className = 'fas fa-circle text-success me-2 flex-shrink-0';
                            statusDot.style.fontSize = '7px';
                            statusDot.title = 'В сети';
                            userCol.appendChild(statusDot);

                            var nameSpan = document.createElement('span');
                            nameSpan.className = 'text-truncate online-user-name';
                            nameSpan.textContent = username;
                            nameSpan.title = username;
                            userCol.appendChild(nameSpan);

                            // Иконки устройств с детальными подсказками
                            var devWrap = document.createElement('span');
                            devWrap.className = 'd-inline-flex align-items-center gap-1 ms-1 flex-shrink-0 online-user-devices';
                            devices.forEach(function (dev) {
                                var devTitleParts = [];
                                if (dev.device_type) devTitleParts.push(dev.device_type);
                                if (dev.os_name && dev.os_name !== 'Не определена') devTitleParts.push(dev.os_name);
                                if (dev.browser_name) devTitleParts.push(dev.browser_name);
                                var devTitle = devTitleParts.join(' • ') || 'Устройство';

                                var devIcon = document.createElement('i');
                                devIcon.className = (dev.device_icon || 'bx bx-laptop') + ' online-device-icon';
                                devIcon.title = devTitle;
                                devWrap.appendChild(devIcon);
                            });
                            userCol.appendChild(devWrap);
                            li.appendChild(userCol);

                            // Правая колонка: иконка отправки сообщения в 1 клик
                            var msgBtn = document.createElement('button');
                            msgBtn.type = 'button';
                            msgBtn.className = 'btn btn-sm btn-link p-0 text-primary online-user-msg-btn flex-shrink-0 ms-1';
                            msgBtn.title = 'Написать сообщение';
                            msgBtn.setAttribute('aria-label', 'Написать сообщение для ' + username);
                            msgBtn.innerHTML = '<i class="bx bx-message-rounded-dots" style="font-size: 17px;"></i>';
                            msgBtn.addEventListener('click', function (e) {
                                e.preventDefault();
                                e.stopPropagation();
                                window.openModal(username, userId);
                            });
                            li.appendChild(msgBtn);

                            // Резервный двойной клик на строку для обратной совместимости
                            li.addEventListener('dblclick', function (e) {
                                e.preventDefault();
                                window.openModal(username, userId);
                            });

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
    // 5. Таймер неактивности пользователя (Auto-Lock Screen) - Отключен
    // =========================================================================
    // Автоматическая блокировка экрана при долгом отсутствии отключена.
    // Сохранена только возможность ручной блокировки пользователем.
    function initInactivityTimer(lockUrl) {
        // Функция оставлена как заглушка для обратной совместимости вызовов.
        return;
    }

    window.initPortalInactivityTimer = initInactivityTimer;

})();
