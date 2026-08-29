// static/admin_templates/js/flight_planning.js

// Получение CSRF токена
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Глобальные переменные для модальных окон
let modalConfirmCallback = null;
let modalCancelCallback = null;
let conflictResolveCallback = null;
let conflictCancelCallback = null;

// Универсальное модальное окно
function showModal(options) {
    const $overlay = $('#modalOverlay');
    const $window = $('#modalWindow');
    const $header = $('#modalHeader');
    const $title = $('#modalTitle');
    const $body = $('#modalBody');
    const $cancelBtn = $('#modalCancelBtn');
    const $confirmBtn = $('#modalConfirmBtn');

    $header.removeClass('error-modal success-modal info-modal warning-modal');
    if (options.type === 'error') {
        $header.addClass('error-modal');
    } else if (options.type === 'success') {
        $header.addClass('success-modal');
    } else if (options.type === 'info') {
        $header.addClass('info-modal');
    } else if (options.type === 'warning') {
        $header.addClass('warning-modal');
    }

    $title.text(options.title || 'Информация');
    $body.html(options.message || '');

    if (options.showCancel === false) {
        $cancelBtn.hide();
    } else {
        $cancelBtn.show();
    }

    if (options.showConfirm === false) {
        $confirmBtn.hide();
    } else {
        $confirmBtn.show();
        $confirmBtn.text(options.confirmText || 'OK');
    }

    modalConfirmCallback = options.onConfirm || function () { closeModal(); };
    modalCancelCallback = options.onCancel || function () { closeModal(); };

    $confirmBtn.off('click').on('click', function () {
        const cb = modalConfirmCallback;
        closeModal();
        if (cb) cb();
    });

    $cancelBtn.off('click').on('click', function () {
        const cb = modalCancelCallback;
        closeModal();
        if (cb) cb();
    });

    $overlay.off('click').on('click', function () {
        const cb = modalCancelCallback;
        closeModal();
        if (cb) cb();
    });

    $overlay.show();
    $window.show();
}

function closeModal() {
    $('#modalOverlay').hide();
    $('#modalWindow').hide();
    modalConfirmCallback = null;
    modalCancelCallback = null;
}

// Модальное окно разрешения конфликтов (занятость на другом МПД или в другом экипаже)
function showConflictModal(conflictData, onConfirm, onCancel) {
    const $overlay = $('#conflictOverlay');
    const $window = $('#conflictModalWindow');
    const $list = $('#conflictList');

    $list.html('');
    if (conflictData && conflictData.conflicts && conflictData.conflicts.length > 0) {
        conflictData.conflicts.forEach(c => {
            const dateTitle = c.date_formatted || c.date;
            const pilotInfo = c.pilot_name ? ` — <strong>${c.pilot_name}</strong>` : '';
            const desc = c.description || (c.old_mpd_name ? `Назначен на «${c.old_mpd_name}»` : '');
            let statusBadge = '';
            if (c.conflict_kind === 'employee_status') {
                const color = c.status_color || '#ef4444';
                statusBadge = `<span class="badge ms-2" style="background-color: ${color}; color: #ffffff; font-size: 0.75rem;">${c.status_name || 'Особый статус'}</span>`;
            }
            $list.append(`
                <div class="conflict-item">
                    <div class="conflict-date-title">📅 ${dateTitle}${pilotInfo}${statusBadge}</div>
                    <div class="conflict-desc">${desc}</div>
                </div>
            `);
        });
    } else if (conflictData && conflictData.errors) {
        conflictData.errors.forEach(err => {
            $list.append(`
                <div class="conflict-item">
                    <div class="conflict-desc">⚠️ ${err}</div>
                </div>
            `);
        });
    }

    conflictResolveCallback = onConfirm;
    conflictCancelCallback = onCancel;

    $('#conflictConfirmBtn').off('click').on('click', function () {
        closeConflictModal();
        if (conflictResolveCallback) conflictResolveCallback();
    });

    $('#conflictCancelBtn').off('click').on('click', function () {
        closeConflictModal();
        if (conflictCancelCallback) conflictCancelCallback();
    });

    $overlay.off('click').on('click', function () {
        closeConflictModal();
        if (conflictCancelCallback) conflictCancelCallback();
    });

    $overlay.show();
    $window.show();
}

function closeConflictModal() {
    $('#conflictOverlay').hide();
    $('#conflictModalWindow').hide();
}

// Модальное окно для выбора пилотов на удаление
function showDeleteSelectionModal(pilotsList, onConfirm) {
    const $overlay = $('#modalOverlay');
    const $window = $('#modalWindow');
    const $header = $('#modalHeader');
    const $title = $('#modalTitle');
    const $body = $('#modalBody');
    const $cancelBtn = $('#modalCancelBtn');
    const $confirmBtn = $('#modalConfirmBtn');

    $header.removeClass('error-modal success-modal info-modal warning-modal').addClass('warning-modal');
    $title.text('Удаление назначений');

    let checklistHtml = '<div style="max-height: 300px; overflow-y: auto;"><p>Выберите пилотов для удаления:</p><ul style="list-style: none; padding-left: 0;">';

    const groupedByDate = {};
    pilotsList.forEach(pilot => {
        if (!groupedByDate[pilot.date]) {
            groupedByDate[pilot.date] = [];
        }
        groupedByDate[pilot.date].push(pilot);
    });

    const sortedDates = Object.keys(groupedByDate).sort();

    for (const date of sortedDates) {
        checklistHtml += `<li style="margin-top: 10px;"><strong>📅 ${date}:</strong><ul style="list-style: none; padding-left: 20px;">`;
        for (const pilot of groupedByDate[date]) {
            checklistHtml += `
                <li style="margin: 5px 0;">
                    <label>
                        <input type="checkbox" class="delete-pilot-checkbox" 
                               data-assignment-id="${pilot.assignment_id}" 
                               data-pilot-id="${pilot.pilot_id}"
                               data-pilot-name="${pilot.pilot_name}"
                               data-date="${pilot.date}"
                               data-mpd-id="${pilot.mpd_id}">
                        ${pilot.pilot_name}
                    </label>
                </li>`;
        }
        checklistHtml += `</ul></li>`;
    }

    checklistHtml += '</ul><div class="select-all-container" style="margin-top: 15px; padding-top: 10px; border-top: 1px solid #eee;">';
    checklistHtml += '<label><input type="checkbox" id="selectAllCheckbox"> Выбрать всех</label>';
    checklistHtml += '</div></div>';

    $body.html(checklistHtml);
    $cancelBtn.show();
    $confirmBtn.show();
    $confirmBtn.text('Удалить выбранных');

    setTimeout(() => {
        $('#selectAllCheckbox').off('change').on('change', function () {
            $('.delete-pilot-checkbox').prop('checked', $(this).prop('checked'));
        });
    }, 50);

    modalConfirmCallback = function () {
        const selectedAssignments = [];
        $('.delete-pilot-checkbox:checked').each(function () {
            selectedAssignments.push({
                assignment_id: $(this).data('assignment-id'),
                pilot_id: $(this).data('pilot-id'),
                pilot_name: $(this).data('pilot-name'),
                date: $(this).data('date'),
                mpd_id: $(this).data('mpd-id')
            });
        });

        if (selectedAssignments.length === 0) {
            showModal({
                title: 'Нет выбора',
                message: 'Не выбрано ни одного пилота для удаления',
                type: 'warning',
                showCancel: false
            });
            return;
        }

        if (onConfirm) {
            onConfirm(selectedAssignments);
        }
        closeModal();
    };

    modalCancelCallback = function () {
        closeModal();
    };

    $confirmBtn.off('click').on('click', function () {
        if (modalConfirmCallback) modalConfirmCallback();
    });

    $cancelBtn.off('click').on('click', function () {
        if (modalCancelCallback) modalCancelCallback();
    });

    $overlay.off('click').on('click', function () {
        if (modalCancelCallback) modalCancelCallback();
    });

    $overlay.show();
    $window.show();
}

$(function () {
    let selectedCells = [];
    let startCell = null;
    let mouseDown = false;
    let isSelecting = false;
    let dragPilot = null;
    let pendingAssignment = null;

    // Очистка выделения
    function clearSelection() {
        $('.plan-cell').removeClass('selected');
        selectedCells = [];
        updateSelectionInfo();
    }

    function updateSelectionInfo() {
        $('#selectedCount').text(`Выделено: ${selectedCells.length} ячеек`);
        if (selectedCells.length > 0) {
            $('#clearSelectionBtn').show();
        } else {
            $('#clearSelectionBtn').hide();
        }
    }

    // Получение ячеек в диапазоне
    function getCellsInRange(start, end) {
        const startRowIndex = $(start).closest('tr').index();
        const endRowIndex = $(end).closest('tr').index();
        const startColIndex = $(start).index();
        const endColIndex = $(end).index();

        const minRow = Math.min(startRowIndex, endRowIndex);
        const maxRow = Math.max(startRowIndex, endRowIndex);
        const minCol = Math.min(startColIndex, endColIndex);
        const maxCol = Math.max(startColIndex, endColIndex);

        const cells = [];
        $('.planning-table tbody tr').each(function (rowIdx) {
            if (rowIdx >= minRow && rowIdx <= maxRow) {
                $(this).find('td.plan-cell').each(function () {
                    const actualColIdx = $(this).index();
                    if (actualColIdx >= minCol && actualColIdx <= maxCol) {
                        cells.push(this);
                    }
                });
            }
        });
        return cells;
    }

    // Обработка выделения мышкой
    $(document).on('mousedown', '.plan-cell', function (e) {
        if (e.which !== 1) return;
        if ($(e.target).closest('.crew-block, .employee-badge, button, a').length > 0) return;
        e.preventDefault();
        mouseDown = true;
        isSelecting = true;
        startCell = this;
        clearSelection();
        $(this).addClass('selected');
        selectedCells.push(this);
        updateSelectionInfo();
    });

    $(document).on('mouseenter', '.plan-cell', function () {
        if (mouseDown && isSelecting && startCell && this !== startCell) {
            const cells = getCellsInRange(startCell, this);
            clearSelection();
            cells.forEach(cell => {
                $(cell).addClass('selected');
                selectedCells.push(cell);
            });
            updateSelectionInfo();
        }
    });

    $(document).on('mouseup', function () {
        setTimeout(() => {
            mouseDown = false;
            isSelecting = false;
            startCell = null;
        }, 10);
    });

    // Добавление бейджа пилота в ячейку
    function addPilotToCell($cell, pilotId, pilotName, assignmentId, jobName, isCommander, isInstructor) {
        const $container = $cell.find('.pilots-container');
        const existingBadge = $container.find(`.employee-badge[data-pilot-id="${pilotId}"]`);
        if (existingBadge.length > 0) return false;

        let displayText = jobName || pilotName;
        if (displayText.length > 15) {
            displayText = displayText.substring(0, 15) + '...';
        }

        let extraClass = '';
        if (isCommander === true || isCommander === 'true') extraClass += ' commander';
        if (isInstructor === true || isInstructor === 'true') extraClass += ' instructor';

        const $badge = $(`
            <span class="employee-badge ${extraClass}"
                  data-pilot-id="${pilotId}"
                  data-assignment-id="${assignmentId}"
                  data-pilot-name="${pilotName}"
                  data-pilot-job="${jobName || ''}"
                  data-is-commander="${isCommander}"
                  data-is-instructor="${isInstructor}">
                ${displayText}
            </span>
        `);

        $container.append($badge);
        $cell.addClass('assigned');
        return true;
    }

    // Удаление бейджа пилота из ячейки
    function removePilotFromCell($cell, pilotId) {
        const $container = $cell.find('.pilots-container');
        const $badge = $container.find(`.employee-badge[data-pilot-id="${pilotId}"]`);
        if ($badge.length > 0) {
            $badge.remove();
            if ($container.find('.employee-badge').length === 0 && $cell.find('.crew-block').length === 0) {
                $cell.removeClass('assigned');
            }
            return true;
        }
        return false;
    }

    // Сбор назначений из выделения
    function collectPilotsFromSelection() {
        const pilots = [];
        selectedCells.forEach(cell => {
            const $cell = $(cell);
            const date = $cell.data('date');
            const mpdId = $cell.data('mpd-id');
            $cell.find('.employee-badge').each(function () {
                pilots.push({
                    pilot_id: $(this).data('pilot-id'),
                    pilot_name: $(this).data('pilot-name'),
                    assignment_id: $(this).data('assignment-id'),
                    date: date,
                    mpd_id: mpdId
                });
            });
        });
        return pilots;
    }

    // Удаление выбранных пилотов
    function deleteSelectedPilots(selectedPilots) {
        const assignmentIds = selectedPilots.map(p => p.assignment_id);
        showModal({
            title: 'Загрузка',
            message: 'Удаление назначений...',
            type: 'info',
            showCancel: false,
            showConfirm: false
        });

        $.ajax({
            url: '/flight/api/remove/',
            method: 'POST',
            headers: {'X-CSRFToken': getCookie('csrftoken')},
            data: JSON.stringify({ assignment_ids: assignmentIds }),
            contentType: 'application/json',
            success: function (response) {
                closeModal();
                if (response.status === 'success') {
                    selectedPilots.forEach(pilot => {
                        const $cell = $(`.plan-cell[data-date="${pilot.date}"][data-mpd-id="${pilot.mpd_id}"]`);
                        removePilotFromCell($cell, pilot.pilot_id);
                    });
                    clearSelection();
                    showModal({
                        title: 'Успешно',
                        message: `Удалено назначений: ${response.deleted}`,
                        type: 'success',
                        showCancel: false
                    });
                }
            },
            error: function (xhr) {
                closeModal();
                showModal({
                    title: 'Ошибка',
                    message: 'Ошибка при удалении: ' + (xhr.responseJSON?.error || 'Неизвестная ошибка'),
                    type: 'error',
                    showCancel: false
                });
            }
        });
    }

    function deleteSelectedAssignments() {
        if (selectedCells.length === 0) {
            showModal({
                title: 'Нет выделения',
                message: 'Нет выделенных ячеек для удаления',
                type: 'warning',
                showCancel: false
            });
            return;
        }

        const pilots = collectPilotsFromSelection();
        if (pilots.length === 0) {
            showModal({
                title: 'Нет назначений',
                message: 'В выделенных ячейках нет индивидуальных назначений для удаления',
                type: 'warning',
                showCancel: false
            });
            return;
        }

        showDeleteSelectionModal(pilots, function (selectedPilots) {
            deleteSelectedPilots(selectedPilots);
        });
    }

    $(document).on('click', '#clearSelectionBtn', function () {
        deleteSelectedAssignments();
    });

    $(document).on('keydown', function (e) {
        if (e.key === 'Delete' && selectedCells.length > 0) {
            e.preventDefault();
            deleteSelectedAssignments();
        }
    });

    // Редактирование экипажа
    $(document).on('click', '.btn-edit-crew', function (e) {
        e.preventDefault();
        e.stopPropagation();
        const crewId = $(this).data('crew-id');
        const dateStr = $(this).data('date');
        const mpdId = $(this).data('mpd-id');
        openCrewBuilderForEdit(crewId, mpdId, dateStr);
    });

    // Клик по шапке экипажа открывает редактирование (для планировщиков) или пометки/инфо (для остальных)
    $(document).on('click', '.crew-header', function (e) {
        if ($(e.target).closest('.btn-delete-crew, .btn-crew-note').length > 0) return;
        const crewId = $(this).data('crew-id');
        const $cell = $(this).closest('.plan-cell');
        const dateStr = $cell.data('date');
        const mpdId = $cell.data('mpd-id');
        if (crewId) {
            if (window.IS_PLANNER === false) {
                openCrewNoteModal(crewId);
            } else {
                openCrewBuilderForEdit(crewId, mpdId, dateStr);
            }
        }
    });

    // Удаление одного экипажа
    $(document).on('click', '.btn-delete-crew', function (e) {
        e.preventDefault();
        e.stopPropagation();
        const crewId = $(this).data('crew-id');
        const $crewBlock = $(this).closest('.crew-block');

        showModal({
            title: 'Расформирование экипажа',
            message: 'Вы действительно хотите расформировать данный экипаж на этот день?',
            type: 'warning',
            confirmText: 'Расформировать',
            onConfirm: function () {
                $.ajax({
                    url: '/flight/api/crew/delete/',
                    method: 'POST',
                    headers: {'X-CSRFToken': getCookie('csrftoken')},
                    data: JSON.stringify({ crew_id: crewId }),
                    contentType: 'application/json',
                    success: function (response) {
                        if (response.status === 'success') {
                            $crewBlock.fadeOut(200, function () { $(this).remove(); });
                            showModal({
                                title: 'Успешно',
                                message: 'Экипаж расформирован',
                                type: 'success',
                                showCancel: false
                            });
                        }
                    },
                    error: function (xhr) {
                        showModal({
                            title: 'Ошибка',
                            message: xhr.responseJSON?.error || 'Ошибка при расформировании экипажа',
                            type: 'error',
                            showCancel: false
                        });
                    }
                });
            }
        });
    });

    // ========================================================
    // ПОМЕТКИ И СООБЩЕНИЯ К ЭКИПАЖУ / ПОЛЕТУ
    // ========================================================
    $(document).on('click', '.btn-crew-note', function (e) {
        e.preventDefault();
        e.stopPropagation();
        const crewId = $(this).data('crew-id');
        if (crewId) {
            openCrewNoteModal(crewId);
        }
    });

    function openCrewNoteModal(crewId) {
        showModal({
            title: 'Загрузка',
            message: 'Загрузка сообщений к рейсу...',
            type: 'info',
            showCancel: false,
            showConfirm: false
        });

        $.ajax({
            url: `/flight/api/crew/${crewId}/notes/`,
            method: 'GET',
            success: function (res) {
                closeModal();
                if (res.status === 'success') {
                    $('#cnCrewId').val(res.crew_id);
                    $('#cnAircraftNumber').text('✈ ' + res.aircraft_number);
                    $('#cnMpdName').text(res.mpd_name);
                    $('#cnDate').text(res.date_formatted);

                    // Статус доступности ввода (вчера, сегодня, завтра + только назначенный экипаж)
                    const $badge = $('#cnDateStatusBadge');
                    const $formContainer = $('#cnAddNoteFormContainer');
                    const $submitBtn = $('#cnSubmitBtn');
                    const $alert = $('#cnDateRestrictedAlert');

                    if (res.can_user_add_note) {
                        $badge.removeClass('bg-secondary bg-warning').addClass('bg-success').text('Ввод доступен');
                        $formContainer.show();
                        $submitBtn.show();
                        $alert.hide();
                    } else {
                        $badge.removeClass('bg-success').addClass('bg-secondary').text('Только просмотр');
                        $formContainer.hide();
                        $submitBtn.hide();
                        $alert.show();

                        if (!res.is_date_allowed) {
                            $alert.html("<i class='bx bx-info-circle me-1'></i> Добавление пометок ограничено: разрешено только для рейсов на вчера, сегодня и завтра.");
                        } else if (!res.is_crew_member && !res.is_admin) {
                            $alert.html("<i class='bx bx-lock-alt me-1'></i> <strong>Доступ ограничен:</strong> Оставлять пометки к полету разрешено только назначенному второму пилоту (членам назначенного экипажа).");
                        }
                    }

                    // Отрисовываем историю пометок
                    renderCrewNotesHistory(res.notes);
                    $('#cnMessageInput').val('');

                    $('#crewNoteOverlay').show();
                    $('#crewNoteModal').show();
                }
            },
            error: function (xhr) {
                closeModal();
                showModal({
                    title: 'Ошибка',
                    message: xhr.responseJSON?.error || 'Не удалось загрузить пометки',
                    type: 'error',
                    showCancel: false
                });
            }
        });
    }

    function renderCrewNotesHistory(notes) {
        const $history = $('#cnNotesHistory');
        $history.empty();

        if (!notes || notes.length === 0) {
            $history.html('<div class="text-muted text-center py-2 small">Пометок к этому рейсу пока нет.</div>');
            return;
        }

        notes.forEach(n => {
            const roleLabel = n.author_role_label ? ` [${n.author_role_label}]` : '';
            const delBtn = n.can_delete ? `<button type="button" class="crew-note-del-btn" data-note-id="${n.id}" title="Удалить пометку">×</button>` : '';

            const itemHtml = `
                <div class="crew-note-item" id="note_item_${n.id}">
                    <div class="crew-note-meta">
                        <div>
                            <span class="crew-note-author">${n.author_name}</span>
                            <span class="badge bg-light text-dark ms-1">${roleLabel}</span>
                        </div>
                        <div>
                            <span class="crew-note-time me-2">${n.created_at}</span>
                            ${delBtn}
                        </div>
                    </div>
                    <div class="crew-note-text">${n.message}</div>
                </div>
            `;
            $history.append(itemHtml);
        });
    }

    function closeCrewNoteModal() {
        $('#crewNoteOverlay').hide();
        $('#crewNoteModal').hide();
    }

    $(document).on('click', '#closeCrewNoteCross, #cnCloseBtn, #crewNoteOverlay', function (e) {
        if (e.target === this) {
            closeCrewNoteModal();
        }
    });

    // Отправка пометки к полету
    $(document).on('click', '#cnSubmitBtn', function () {
        const crewId = $('#cnCrewId').val();
        const message = $('#cnMessageInput').val().trim();

        if (!message) {
            showModal({
                title: 'Пустое сообщение',
                message: 'Введите текст пометки к полету',
                type: 'warning',
                showCancel: false
            });
            return;
        }

        showModal({
            title: 'Отправка',
            message: 'Сохранение пометки...',
            type: 'info',
            showCancel: false,
            showConfirm: false
        });

        $.ajax({
            url: `/flight/api/crew/${crewId}/notes/add/`,
            method: 'POST',
            headers: {'X-CSRFToken': getCookie('csrftoken')},
            data: JSON.stringify({ message: message }),
            contentType: 'application/json',
            success: function (res) {
                closeModal();
                if (res.status === 'success') {
                    $('#cnMessageInput').val('');
                    // Перезагружаем список
                    openCrewNoteModal(crewId);
                    showModal({
                        title: 'Успешно',
                        message: 'Пометка к полету сохранена',
                        type: 'success',
                        showCancel: false,
                        onConfirm: function () { window.location.reload(); }
                    });
                }
            },
            error: function (xhr) {
                closeModal();
                showModal({
                    title: 'Ошибка',
                    message: xhr.responseJSON?.error || 'Ошибка при сохранении пометки',
                    type: 'error',
                    showCancel: false
                });
            }
        });
    });

    // Удаление пометки к полету
    $(document).on('click', '.crew-note-del-btn', function (e) {
        e.preventDefault();
        e.stopPropagation();
        const noteId = $(this).data('note-id');

        showModal({
            title: 'Удаление пометки',
            message: 'Вы уверены, что хотите удалить эту пометку?',
            type: 'warning',
            confirmText: 'Удалить',
            onConfirm: function () {
                $.ajax({
                    url: `/flight/api/crew/notes/${noteId}/delete/`,
                    method: 'POST',
                    headers: {'X-CSRFToken': getCookie('csrftoken')},
                    contentType: 'application/json',
                    success: function (res) {
                        if (res.status === 'success') {
                            $(`#note_item_${noteId}`).fadeOut(200, function () { $(this).remove(); });
                            showModal({
                                title: 'Успешно',
                                message: 'Пометка удалена',
                                type: 'success',
                                showCancel: false,
                                onConfirm: function () { window.location.reload(); }
                            });
                        }
                    },
                    error: function (xhr) {
                        showModal({
                            title: 'Ошибка',
                            message: xhr.responseJSON?.error || 'Ошибка удаления пометки',
                            type: 'error',
                            showCancel: false
                        });
                    }
                });
            }
        });
    });

    // Drag-and-drop для пилотов (только при наличии прав планирования)
    if (window.IS_PLANNER !== false) {
        $('.pilot-item').draggable({
            revert: 'invalid',
            cursor: 'move',
            helper: 'clone',
            opacity: 0.75,
            start: function () {
                dragPilot = {
                    id: $(this).data('pilot-id'),
                    name: $(this).data('pilot-name'),
                    job: $(this).data('pilot-job'),
                    isCommander: $(this).data('is-commander'),
                    isInstructor: $(this).data('is-instructor')
                };
            }
        });

        // Droppable для ячеек
        $('.plan-cell').droppable({
            accept: '.pilot-item',
            tolerance: 'pointer',
            drop: function (e, ui) {
                if (!dragPilot) return;

                let targetCells = selectedCells;
                if (targetCells.length === 0) {
                    targetCells = [this];
                }

                const mpdIds = [...new Set(targetCells.map(cell => $(cell).data('mpd-id')))];
                if (mpdIds.length > 1) {
                    showModal({
                        title: 'Ошибка',
                        message: 'Нельзя назначить пилота на разные МПД одновременно',
                        type: 'error',
                        showCancel: false
                    });
                    return;
                }

                const mpdId = mpdIds[0];
                const mpdName = $(targetCells[0]).data('mpd-name') || 'МПД';
                const dates = targetCells.map(cell => $(cell).data('date')).sort();
                const startDate = dates[0];
                const endDate = dates[dates.length - 1];

                checkAndOpenAssignChoice(dragPilot, mpdId, mpdName, startDate, endDate, targetCells);
            }
        });
    } else {
        // Для наблюдателей/пилотов курсор обычный
        $('.pilot-item').css('cursor', 'default');
    }

    // ========================================================
    // ВАРИАНТЫ НАЗНАЧЕНИЯ ПРИ DRAG & DROP
    // ========================================================
    function checkAndOpenAssignChoice(pilot, mpdId, mpdName, startDate, endDate, targetCells) {
        $('#acPilotName').text(pilot.name + (pilot.job ? ` (${pilot.job})` : ''));
        $('#acMpdName').text(mpdName);
        $('#acPeriod').text(`${startDate} — ${endDate}`);

        const existingCrews = [];
        if (window.CREW_MAP && window.CREW_MAP[mpdId]) {
            const mpdCrews = window.CREW_MAP[mpdId];
            datesInRange(startDate, endDate).forEach(dStr => {
                if (mpdCrews[dStr]) {
                    mpdCrews[dStr].forEach(cr => {
                        if (!existingCrews.some(c => c.id === cr.id)) {
                            existingCrews.push(cr);
                        }
                    });
                }
            });
        }

        const $crewsContainer = $('#acExistingCrewsContainer');
        const $crewSelect = $('#acCrewSelect');
        $crewSelect.empty();

        if (existingCrews.length > 0) {
            existingCrews.forEach(c => {
                $crewSelect.append(`<option value="${c.id}">Экипаж ${c.aircraft_number} (${c.flight_type_label})</option>`);
            });
            $crewsContainer.show();
        } else {
            $crewsContainer.hide();
        }

        let defRole = 'copilot';
        const jobLower = (pilot.job || '').toLowerCase();
        if (jobLower.includes('командир')) defRole = 'commander';
        else if (jobLower.includes('бортмеханик-инструктор')) defRole = 'flight_engineer_instructor';
        else if (jobLower.includes('бортмеханик') || jobLower.includes('механик')) defRole = 'flight_engineer';
        else if (jobLower.includes('инструктор')) defRole = 'pilot_instructor';
        $('#acRoleSelect').val(defRole);

        $(document).off('click', '#acJoinCrewBtn').on('click', '#acJoinCrewBtn', function () {
            const crewId = $('#acCrewSelect').val();
            const role = $('#acRoleSelect').val();
            closeAssignChoiceModal();
            joinExistingCrew(crewId, pilot.id, role, false);
        });

        $(document).off('click', '#acCreateCrewCard').on('click', '#acCreateCrewCard', function () {
            closeAssignChoiceModal();
            openCrewBuilder(mpdId, startDate, endDate, pilot.id, defRole);
        });

        $(document).off('click', '#acStandaloneAssignCard').on('click', '#acStandaloneAssignCard', function () {
            closeAssignChoiceModal();
            performStandaloneAssign(pilot, mpdId, startDate, endDate, targetCells);
        });

        $(document).off('click', '#acCancelBtn, #assignChoiceOverlay').on('click', '#acCancelBtn, #assignChoiceOverlay', closeAssignChoiceModal);

        $('#assignChoiceOverlay').show();
        $('#assignChoiceModal').show();
    }

    function closeAssignChoiceModal() {
        $('#assignChoiceOverlay').hide();
        $('#assignChoiceModal').hide();
    }

    function joinExistingCrew(crewId, pilotId, role, forceOverride) {
        showModal({
            title: 'Загрузка',
            message: 'Включение в экипаж...',
            type: 'info',
            showCancel: false,
            showConfirm: false
        });

        $.ajax({
            url: '/flight/api/crew/add-member/',
            method: 'POST',
            headers: {'X-CSRFToken': getCookie('csrftoken')},
            data: JSON.stringify({
                crew_id: crewId,
                pilot_id: pilotId,
                role: role,
                force_override: forceOverride === true
            }),
            contentType: 'application/json',
            success: function (response) {
                closeModal();
                showModal({
                    title: 'Успешно',
                    message: response.message || 'Сотрудник добавлен в экипаж',
                    type: 'success',
                    showCancel: false,
                    onConfirm: function () { window.location.reload(); }
                });
            },
            error: function (xhr) {
                closeModal();
                if (xhr.status === 409 && xhr.responseJSON?.status === 'conflict') {
                    const conflictData = xhr.responseJSON;
                    if (conflictData.can_override) {
                        showConflictModal(
                            conflictData,
                            function onConfirmOverride() {
                                joinExistingCrew(crewId, pilotId, role, true);
                            }
                        );
                        return;
                    }
                }
                showModal({
                    title: 'Ошибка',
                    message: xhr.responseJSON?.error || 'Ошибка добавления в экипаж',
                    type: 'error',
                    showCancel: false
                });
            }
        });
    }

    function performStandaloneAssign(pilot, mpdId, startDate, endDate, targetCells) {
        showModal({
            title: 'Загрузка',
            message: 'Назначение сотрудника...',
            type: 'info',
            showCancel: false,
            showConfirm: false
        });

        $.ajax({
            url: '/flight/api/assign/',
            method: 'POST',
            headers: {'X-CSRFToken': getCookie('csrftoken')},
            data: JSON.stringify({
                pilot_id: pilot.id,
                mpd_id: mpdId,
                start_date: startDate,
                end_date: endDate
            }),
            contentType: 'application/json',
            success: function (response) {
                closeModal();
                if (response.status === 'success') {
                    targetCells.forEach(cell => {
                        const $cell = $(cell);
                        const cellDate = $cell.data('date');
                        const assignment = response.assignments.find(a => a.date === cellDate);
                        if (assignment) {
                            addPilotToCell($cell, pilot.id, pilot.name, assignment.assignment_id, pilot.job, pilot.isCommander, pilot.isInstructor);
                        }
                    });
                    clearSelection();
                    showModal({
                        title: 'Успешно',
                        message: `Сотрудник ${pilot.name} назначен на ${response.assignments.length} дн.`,
                        type: 'success',
                        showCancel: false
                    });
                }
            },
            error: function (xhr) {
                closeModal();
                if (xhr.status === 409) {
                    const response = xhr.responseJSON;
                    pendingAssignment = {
                        pilot: pilot,
                        mpdId: mpdId,
                        startDate: startDate,
                        endDate: endDate,
                        conflictData: response,
                        selectedCells: [...targetCells]
                    };
                    showConflictModal(response, function () {
                        resolveConflict(pendingAssignment);
                    });
                } else {
                    showModal({
                        title: 'Ошибка',
                        message: xhr.responseJSON?.error || 'Ошибка назначения',
                        type: 'error',
                        showCancel: false
                    });
                }
            }
        });
    }

    function resolveConflict(pending) {
        showModal({
            title: 'Загрузка',
            message: 'Перезапись назначений...',
            type: 'info',
            showCancel: false,
            showConfirm: false
        });

        $.ajax({
            url: '/flight/api/resolve-conflict/',
            method: 'POST',
            headers: {'X-CSRFToken': getCookie('csrftoken')},
            data: JSON.stringify({
                pilot_id: pending.pilot.id,
                new_mpd_id: pending.mpdId,
                start_date: pending.startDate,
                end_date: pending.endDate,
                conflict_dates: pending.conflictData.conflicts.map(c => c.date)
            }),
            contentType: 'application/json',
            success: function () {
                closeModal();
                showModal({
                    title: 'Успешно',
                    message: 'Конфликты устранены, назначения сохранены',
                    type: 'success',
                    showCancel: false,
                    onConfirm: function () { window.location.reload(); }
                });
            },
            error: function (xhr) {
                closeModal();
                showModal({
                    title: 'Ошибка',
                    message: xhr.responseJSON?.error || 'Ошибка разрешения конфликта',
                    type: 'error',
                    showCancel: false
                });
            }
        });
    }

    function datesInRange(start, end) {
        const dates = [];
        let curr = new Date(start);
        const last = new Date(end);
        while (curr <= last) {
            dates.push(curr.toISOString().split('T')[0]);
            curr.setDate(curr.getDate() + 1);
        }
        return dates;
    }

    // ========================================================
    // МАСТЕР СБОРКИ И РЕДАКТИРОВАНИЯ ЭКИПАЖА (CREW BUILDER)
    // ========================================================
    $(document).on('click', '#openCrewBuilderBtn', function (e) {
        e.preventDefault();
        let defaultMpdId = '';
        let defaultStart = '';
        let defaultEnd = '';

        if (selectedCells.length > 0) {
            defaultMpdId = $(selectedCells[0]).data('mpd-id');
            const dates = selectedCells.map(cell => $(cell).data('date')).sort();
            defaultStart = dates[0];
            defaultEnd = dates[dates.length - 1];
        } else {
            const today = new Date().toISOString().split('T')[0];
            defaultStart = today;
            defaultEnd = today;
        }

        openCrewBuilder(defaultMpdId, defaultStart, defaultEnd);
    });

    // Режим создания нового экипажа
    function openCrewBuilder(mpdId, startDate, endDate, prefilledPilotId, prefilledRole) {
        $('#cbCrewId').val('');
        $('#crewBuilderTitle').html("<i class='bx bx-group me-2'></i> Сборка экипажа ВС");
        $('#cbSubmitBtn').html("<i class='bx bx-check-circle me-1'></i> Сформировать экипаж");

        $('#cbMpdSelect').val(mpdId || '');
        $('#cbStartDate').val(startDate || new Date().toISOString().split('T')[0]);
        $('#cbEndDate').val(endDate || new Date().toISOString().split('T')[0]);
        $('#cbFlightTypeSelect').val('standard');
        $('#cbComment').val('');

        updateAircraftOptions(mpdId, null, startDate, endDate);
        buildRoleSlots('standard', prefilledPilotId, prefilledRole);

        $('#crewBuilderOverlay').show();
        $('#crewBuilderModal').show();
    }

    // Режим редактирования существующего экипажа
    function openCrewBuilderForEdit(crewId, mpdId, dateStr) {
        showModal({
            title: 'Загрузка',
            message: 'Загрузка данных экипажа...',
            type: 'info',
            showCancel: false,
            showConfirm: false
        });

        $.ajax({
            url: `/flight/api/crew/${crewId}/`,
            method: 'GET',
            success: function (response) {
                closeModal();
                if (response.status === 'success' && response.crew) {
                    const crew = response.crew;
                    $('#cbCrewId').val(crew.id);
                    $('#crewBuilderTitle').html(`<i class='bx bx-edit-alt me-2'></i> Редактирование экипажа ${crew.aircraft_number}`);
                    $('#cbSubmitBtn').html("<i class='bx bx-save me-1'></i> Сохранить изменения");

                    $('#cbMpdSelect').val(crew.mpd_id);
                    $('#cbStartDate').val(crew.date);
                    $('#cbEndDate').val(crew.date);
                    $('#cbFlightTypeSelect').val(crew.flight_type);
                    $('#cbComment').val(crew.comment || '');

                    updateAircraftOptions(crew.mpd_id, crew.aircraft_id, crew.date, crew.date);

                    // Формируем слоты под участников экипажа
                    const $container = $('#cbMembersSlotsContainer');
                    $container.empty();

                    if (crew.members && crew.members.length > 0) {
                        crew.members.forEach(m => {
                            addRoleSlot(m.role, getRoleLabel(m.role), m.member_id);
                        });
                    } else {
                        buildRoleSlots(crew.flight_type);
                    }

                    validateCrewLive();

                    $('#crewBuilderOverlay').show();
                    $('#crewBuilderModal').show();
                }
            },
            error: function (xhr) {
                closeModal();
                showModal({
                    title: 'Ошибка',
                    message: xhr.responseJSON?.error || 'Не удалось загрузить данные экипажа',
                    type: 'error',
                    showCancel: false
                });
            }
        });
    }

    function closeCrewBuilder() {
        $('#crewBuilderOverlay').hide();
        $('#crewBuilderModal').hide();
    }

    $(document).on('click', '#closeCrewBuilderCross, #cbCancelBtn, #crewBuilderOverlay', function (e) {
        if (e.target === this) {
            closeCrewBuilder();
        }
    });

    $(document).on('change', '#cbMpdSelect', function () {
        const mpdId = $(this).val();
        updateAircraftOptions(mpdId, $('#cbAircraftSelect').val(), $('#cbStartDate').val(), $('#cbEndDate').val());
    });

    $(document).on('change', '#cbStartDate', function () {
        const startDate = $(this).val();
        let endDate = $('#cbEndDate').val();
        if (endDate && endDate < startDate) {
            $('#cbEndDate').val(startDate);
            endDate = startDate;
        }
        updateAircraftOptions($('#cbMpdSelect').val(), $('#cbAircraftSelect').val(), startDate, endDate);
    });

    $(document).on('change', '#cbEndDate', function () {
        const endDate = $(this).val();
        const startDate = $('#cbStartDate').val();
        updateAircraftOptions($('#cbMpdSelect').val(), $('#cbAircraftSelect').val(), startDate, endDate);
    });

    $(document).on('change', '#cbFlightTypeSelect', function () {
        const flightType = $(this).val();
        buildRoleSlots(flightType);
    });

    /**
     * Вычисляет статус присутствия конкретного ВС на МПД относительно заданных дат.
     */
    function getAircraftBasingStatus(acId, mpdId, startDate, endDate) {
        if (!mpdId) {
            return { isBased: false, isPartial: false, label: '', badge: '', group: 'other' };
        }

        const intervalsMap = window.MPD_AIRCRAFT_INTERVALS_MAP || {};
        const mpdIntervals = intervalsMap[mpdId] || [];
        const matchingIntervals = mpdIntervals.filter(i => i.aircraft_id == acId);

        if (matchingIntervals.length === 0) {
            const allIntervals = window.ALL_AIRCRAFT_INTERVALS || [];
            const acData = allIntervals.find(a => a.id == acId);
            let otherMpdName = '';
            if (acData && acData.intervals && acData.intervals.length > 0) {
                const cur = acData.intervals.find(i => {
                    const iFrom = i.from_date || '0000-00-00';
                    const iTo = i.to_date || '9999-99-99';
                    return startDate >= iFrom && startDate <= iTo;
                }) || acData.intervals[acData.intervals.length - 1];
                if (cur) otherMpdName = cur.mpd_name;
            }
            return {
                isBased: false,
                isPartial: false,
                label: otherMpdName ? `[Базируется на «${otherMpdName}»]` : '',
                badge: '',
                group: 'other'
            };
        }

        const sDate = startDate || '0000-00-00';
        const eDate = endDate || sDate;

        let overlaps = false;
        let coversAll = false;
        let bestInterval = null;

        for (const inter of matchingIntervals) {
            const iFrom = inter.from_date || '0000-00-00';
            const iTo = inter.to_date || '9999-99-99';

            if (sDate <= iTo && eDate >= iFrom) {
                overlaps = true;
                bestInterval = inter;
                if (iFrom <= sDate && iTo >= eDate) {
                    coversAll = true;
                }
            }
        }

        if (coversAll && bestInterval) {
            return {
                isBased: true,
                isPartial: false,
                label: `[на МПД: ${bestInterval.period_label}]`,
                badge: `на МПД ${bestInterval.period_label}`,
                group: 'active'
            };
        } else if (overlaps && bestInterval) {
            return {
                isBased: true,
                isPartial: true,
                label: `[⚠️ на МПД частично: ${bestInterval.period_label}]`,
                badge: `на МПД частично (${bestInterval.period_label})`,
                group: 'active'
            };
        } else {
            const firstInter = matchingIntervals[0];
            return {
                isBased: false,
                isPartial: false,
                label: `[был на этом МПД: ${firstInter.period_label}]`,
                badge: `был на МПД ${firstInter.period_label}`,
                group: 'historical'
            };
        }
    }

    function updateAircraftOptions(mpdId, selectedAircraftId, startDate, endDate) {
        const $acSelect = $('#cbAircraftSelect');
        const currentVal = selectedAircraftId || $acSelect.val();
        $acSelect.empty();
        $acSelect.append('<option value="">— Резервный экипаж (без борта) —</option>');

        const sDate = startDate || $('#cbStartDate').val() || new Date().toISOString().split('T')[0];
        const eDate = endDate || $('#cbEndDate').val() || sDate;
        const currentMpdId = mpdId || $('#cbMpdSelect').val();

        if (!currentMpdId) {
            $('#cbAircraftHint').html('<span class="text-muted">Выберите МПД для загрузки базирующихся ВС</span>');
            return;
        }

        const allAircraft = window.ALL_AIRCRAFT || [];
        const activeGroup = [];
        const historicalGroup = [];
        const otherGroup = [];

        allAircraft.forEach(ac => {
            const status = getAircraftBasingStatus(ac.id, currentMpdId, sDate, eDate);
            const typeStr = ac.type ? ` (${ac.type})` : '';
            const isSelected = currentVal && currentVal == ac.id;

            const optionHtml = `<option value="${ac.id}" ${isSelected ? 'selected' : ''}>✈ ${ac.reg}${typeStr} ${status.label}</option>`;

            if (status.group === 'active') {
                activeGroup.push({ ac, status, html: optionHtml });
            } else if (status.group === 'historical') {
                historicalGroup.push({ ac, status, html: optionHtml });
            } else {
                otherGroup.push({ ac, status, html: optionHtml });
            }
        });

        if (activeGroup.length > 0) {
            const $grp = $('<optgroup label="✈ Базируются на МПД в выбранные даты:"></optgroup>');
            activeGroup.forEach(item => $grp.append(item.html));
            $acSelect.append($grp);
        }

        if (historicalGroup.length > 0) {
            const $grp = $('<optgroup label="🕒 Были на этом МПД в другие даты месяца:"></optgroup>');
            historicalGroup.forEach(item => $grp.append(item.html));
            $acSelect.append($grp);
        }

        if (otherGroup.length > 0) {
            const $grp = $('<optgroup label="Другие воздушные суда авиакомпании:"></optgroup>');
            otherGroup.forEach(item => $grp.append(item.html));
            $acSelect.append($grp);
        }

        // Обновляем подсказку #cbAircraftHint
        if (activeGroup.length === 1 && !activeGroup[0].status.isPartial) {
            const ac = activeGroup[0].ac;
            const st = activeGroup[0].status;
            $('#cbAircraftHint').html(`<span class="text-success font-weight-bold"><i class='bx bx-check-circle me-1'></i>Базируется на МПД: ✈ ${ac.reg} (${st.badge})</span>`);
        } else if (activeGroup.length > 1) {
            const summary = activeGroup.map(item => `✈ ${item.ac.reg} (${item.status.badge})`).join(', ');
            $('#cbAircraftHint').html(`<span class="text-primary font-weight-bold"><i class='bx bx-info-circle me-1'></i>На МПД в этот период: ${summary}</span>`);
        } else if (activeGroup.length === 1 && activeGroup[0].status.isPartial) {
            const ac = activeGroup[0].ac;
            const st = activeGroup[0].status;
            $('#cbAircraftHint').html(`<span class="text-warning font-weight-bold"><i class='bx bx-error-circle me-1'></i>Внимание: ✈ ${ac.reg} (${st.badge})</span>`);
        } else if (historicalGroup.length > 0) {
            const histSummary = historicalGroup.map(item => `✈ ${item.ac.reg} (${item.status.badge})`).join(', ');
            $('#cbAircraftHint').html(`<span class="text-warning"><i class='bx bx-time me-1'></i>На выбранные даты борт перемещен. В этом месяце на МПД были: ${histSummary}</span>`);
        } else {
            $('#cbAircraftHint').html('<span class="text-muted">На данном МПД нет базирующихся ВС на эти даты (будет резервным экипажем)</span>');
        }
    }

    function buildRoleSlots(flightType, prefilledPilotId, prefilledRole) {
        const $container = $('#cbMembersSlotsContainer');
        $container.empty();

        const slotDefinitions = [];
        if (flightType === 'standard') {
            slotDefinitions.push({ role: 'commander', label: 'КВС (Командир ВС)*' });
            slotDefinitions.push({ role: 'copilot', label: 'Второй пилот / 2-й КВС*' });
            slotDefinitions.push({ role: 'flight_engineer', label: 'Бортмеханик*' });
        } else if (flightType === 'check_flight_engineer') {
            slotDefinitions.push({ role: 'commander', label: 'КВС (Командир ВС)*' });
            slotDefinitions.push({ role: 'copilot', label: 'Второй пилот / 2-й КВС*' });
            slotDefinitions.push({ role: 'flight_engineer', label: 'Бортмеханик (проверяемый)*' });
            slotDefinitions.push({ role: 'flight_engineer_instructor', label: 'Бортмеханик-инструктор*' });
        } else if (flightType === 'check_pilot') {
            slotDefinitions.push({ role: 'commander', label: 'КВС (проверяемый/КВС)*' });
            slotDefinitions.push({ role: 'pilot_instructor', label: 'Пилот-инструктор (проверяющий)*' });
            slotDefinitions.push({ role: 'flight_engineer', label: 'Бортмеханик*' });
            slotDefinitions.push({ role: 'copilot', label: 'Второй пилот (опционально)' });
        } else if (flightType === 'double_check') {
            slotDefinitions.push({ role: 'commander', label: 'КВС*' });
            slotDefinitions.push({ role: 'pilot_instructor', label: 'Пилот-инструктор (проверяющий)*' });
            slotDefinitions.push({ role: 'flight_engineer', label: 'Бортмеханик (проверяемый)*' });
            slotDefinitions.push({ role: 'flight_engineer_instructor', label: 'Бортмеханик-инструктор*' });
            slotDefinitions.push({ role: 'copilot', label: 'Второй пилот (опционально)' });
        }

        slotDefinitions.forEach(slot => {
            const isPrefilled = prefilledPilotId && (prefilledRole === slot.role || (!prefilledRole && slot.role === 'commander'));
            addRoleSlot(slot.role, slot.label, isPrefilled ? prefilledPilotId : null);
        });

        validateCrewLive();
    }

    // Добавление слота с фильтрацией кандидатов по должности!
    function addRoleSlot(role, labelText, selectedPilotId) {
        const $container = $('#cbMembersSlotsContainer');
        const slotId = 'slot_' + Math.random().toString(36).substr(2, 9);

        // ФИЛЬТРАЦИЯ СОТРУДНИКОВ ПО ДОЛЖНОСТИ ДЛЯ ВЫБРАННОЙ РОЛИ
        let filteredCandidates = [];
        if (window.ALL_PILOTS) {
            filteredCandidates = window.ALL_PILOTS.filter(p => {
                if (selectedPilotId && selectedPilotId == p.id) return true;
                if (p.allowed_roles && Array.isArray(p.allowed_roles)) {
                    return p.allowed_roles.includes(role);
                }
                return true;
            });
        }

        const startDateVal = $('#cbStartDate').val();
        const endDateVal = $('#cbEndDate').val();

        let optionsHtml = '<option value="">— Выберите сотрудника —</option>';
        filteredCandidates.forEach(p => {
            const sel = (selectedPilotId && selectedPilotId == p.id) ? 'selected' : '';
            const jobBadge = p.job ? ` — [${p.job}]` : '';

            // Индикация активного состояния/статуса сотрудника
            let statusSuffix = '';
            if (window.EMPLOYEE_STATUS_MAP && window.EMPLOYEE_STATUS_MAP[p.id]) {
                const pStatuses = window.EMPLOYEE_STATUS_MAP[p.id];
                const activeSt = pStatuses.find(st => {
                    if (!startDateVal || !endDateVal) return true;
                    return (startDateVal <= st.end_date && endDateVal >= st.start_date);
                });
                if (activeSt) {
                    statusSuffix = ` ⚠️ [${activeSt.status_name}: ${activeSt.period_display}]`;
                }
            }

            optionsHtml += `<option value="${p.id}" ${sel}>${p.name}${jobBadge}${statusSuffix}</option>`;
        });

        const slotHtml = `
            <div class="crew-role-slot" id="${slotId}">
                <label>
                    ${labelText || getRoleLabel(role)}
                    <span class="badge bg-light text-muted ms-1" style="font-size: 0.68rem; font-weight: normal;">(подходит: ${filteredCandidates.length})</span>
                </label>
                <input type="hidden" class="slot-role" value="${role}">
                <select class="slot-pilot-select form-control form-control-modern">
                    ${optionsHtml}
                </select>
                <button type="button" class="btn btn-sm btn-outline-danger py-0 px-2 btn-remove-slot" title="Удалить слот">×</button>
            </div>
        `;
        $container.append(slotHtml);

        $(`#${slotId} .slot-pilot-select`).on('change', validateCrewLive);
        $(`#${slotId} .btn-remove-slot`).on('click', function () {
            $(`#${slotId}`).remove();
            validateCrewLive();
        });
    }

    $(document).on('click', '#cbAddMemberSlotBtn', function () {
        addRoleSlot('copilot', 'Дополнительный член экипажа');
    });

    function getRoleLabel(role) {
        const map = {
            'commander': 'КВС (Командир)',
            'copilot': 'Второй пилот',
            'pilot_instructor': 'Пилот-инструктор',
            'flight_engineer': 'Бортмеханик',
            'flight_engineer_instructor': 'Бортмеханик-инструктор'
        };
        return map[role] || role;
    }

    function validateCrewLive() {
        const flightType = $('#cbFlightTypeSelect').val();
        const startDate = $('#cbStartDate').val();
        const endDate = $('#cbEndDate').val();
        const members = [];

        $('.crew-role-slot').each(function () {
            const role = $(this).find('.slot-role').val();
            const memberId = $(this).find('.slot-pilot-select').val();
            if (memberId) {
                members.push({ member_id: parseInt(memberId), role: role });
            }
        });

        const $alert = $('#cbValidationAlert');
        const $text = $('#cbValidationText');

        if (members.length === 0) {
            $alert.hide();
            return;
        }

        $.ajax({
            url: '/flight/api/crew/validate/',
            method: 'POST',
            headers: {'X-CSRFToken': getCookie('csrftoken')},
            data: JSON.stringify({
                flight_type: flightType,
                members: members,
                start_date: startDate,
                end_date: endDate
            }),
            contentType: 'application/json',
            success: function (res) {
                $alert.show();
                let htmlMessage = '';
                if (res.is_valid) {
                    $alert.removeClass('invalid').addClass('valid');
                    htmlMessage = '✓ <strong>Состав экипажа полностью соответствует правилам</strong>';
                } else {
                    $alert.removeClass('valid').addClass('invalid');
                    htmlMessage = '⚠️ ' + (res.errors ? res.errors.join('<br>⚠️ ') : 'Ошибка валидации');
                }

                if (res.status_warnings && res.status_warnings.length > 0) {
                    htmlMessage += '<div class="mt-2 pt-2 border-top text-warning fw-bold"><i class="bx bx-error me-1"></i>Предупреждение о статусах занятости персонала:<br>• ' + res.status_warnings.join('<br>• ') + '</div>';
                }
                $text.html(htmlMessage);
            },
            error: function () {
                $alert.hide();
            }
        });
    }

    // Сохранение экипажа (создание или обновление с обработкой конфликтов)
    function submitCrewForm(forceOverride) {
        const crewId = $('#cbCrewId').val() || null;
        const mpdId = $('#cbMpdSelect').val();
        const aircraftId = $('#cbAircraftSelect').val() || null;
        const startDate = $('#cbStartDate').val();
        const endDate = $('#cbEndDate').val();
        const flightType = $('#cbFlightTypeSelect').val();
        const comment = $('#cbComment').val();

        if (!mpdId || !startDate || !endDate) {
            showModal({
                title: 'Не все поля заполнены',
                message: 'Укажите МПД и диапазон дат для формирования экипажа',
                type: 'warning',
                showCancel: false
            });
            return;
        }

        const members = [];
        $('.crew-role-slot').each(function () {
            const role = $(this).find('.slot-role').val();
            const memberId = $(this).find('.slot-pilot-select').val();
            if (memberId) {
                members.push({ member_id: parseInt(memberId), role: role });
            }
        });

        if (members.length === 0) {
            showModal({
                title: 'Пустой экипаж',
                message: 'Выберите сотрудников в состав экипажа',
                type: 'warning',
                showCancel: false
            });
            return;
        }

        // Предупреждение о статусах занятости персонала (Отпуск, Больничный, Резерв, КПК, ВЛЭК и др.)
        if (!forceOverride && window.EMPLOYEE_STATUS_MAP) {
            let statusWarnings = [];
            members.forEach(m => {
                const pStatuses = window.EMPLOYEE_STATUS_MAP[m.member_id];
                if (pStatuses && Array.isArray(pStatuses)) {
                    const activeSt = pStatuses.find(st => (startDate <= st.end_date && endDate >= st.start_date));
                    if (activeSt && activeSt.is_blocking) {
                        const pilotObj = window.ALL_PILOTS ? window.ALL_PILOTS.find(p => p.id === m.member_id) : null;
                        const pName = pilotObj ? pilotObj.name : `Сотрудник #${m.member_id}`;
                        const docInfo = activeSt.document_number ? ` (док. №${activeSt.document_number})` : '';
                        statusWarnings.push(`• <strong>${pName}</strong>: статус «${activeSt.status_name}» (${activeSt.period_display})${docInfo}`);
                    }
                }
            });

            if (statusWarnings.length > 0) {
                showModal({
                    title: '⚠️ Предупреждение: статус занятости сотрудника',
                    message: `Внимание: Следующие сотрудники находятся в особом статусе/состоянии на выбранные даты:<br><br>${statusWarnings.join('<br>')}<br><br><span class="text-muted small">Вы действительно хотите назначить сотрудника в экипаж?</span>`,
                    type: 'warning',
                    showCancel: true,
                    confirmText: 'Все равно сохранить',
                    cancelText: 'Отмена',
                    onConfirm: function () {
                        submitCrewForm(true);
                    }
                });
                return;
            }
        }

        // Рекомендательная проверка сроков действия периодических проверок персонала
        if (!forceOverride && window.PILOTS_CHECK_STATUS_MAP) {
            let checkWarnings = [];
            members.forEach(m => {
                const pStatus = window.PILOTS_CHECK_STATUS_MAP[m.member_id];
                if (pStatus && (pStatus.has_expired || pStatus.has_missing)) {
                    const pilotObj = window.ALL_PILOTS ? window.ALL_PILOTS.find(p => p.id === m.member_id) : null;
                    const pName = pilotObj ? pilotObj.name : `Сотрудник #${m.member_id}`;
                    checkWarnings.push(`• <strong>${pName}</strong>: ${pStatus.summary_text || 'Просрочены/не пройдены мероприятия'}`);
                }
            });

            if (checkWarnings.length > 0) {
                showModal({
                    title: '⚠️ Предупреждение: периодические мероприятия',
                    message: `Внимание: У следующих членов экипажа имеются непройденные или просроченные периодические мероприятия:<br><br>${checkWarnings.join('<br>')}<br><br><span class="text-muted small">Назначение носит рекомендательный характер. Назначенный сотрудник будет отмечен предупреждающим значком ⚠️ в сетке планирования.</span><br><br>Продолжить сохранение экипажа?`,
                    type: 'warning',
                    showCancel: true,
                    confirmText: 'Все равно сохранить',
                    cancelText: 'Отмена',
                    onConfirm: function () {
                        submitCrewForm(true);
                    }
                });
                return;
            }
        }

        showModal({
            title: crewId ? 'Сохранение экипажа' : 'Формирование экипажа',
            message: 'Сохранение данных экипажа...',
            type: 'info',
            showCancel: false,
            showConfirm: false
        });

        $.ajax({
            url: '/flight/api/crew/save/',
            method: 'POST',
            headers: {'X-CSRFToken': getCookie('csrftoken')},
            data: JSON.stringify({
                crew_id: crewId ? parseInt(crewId) : null,
                mpd_id: parseInt(mpdId),
                aircraft_id: aircraftId ? parseInt(aircraftId) : null,
                start_date: startDate,
                end_date: endDate,
                flight_type: flightType,
                members: members,
                comment: comment,
                force_override: forceOverride === true
            }),
            contentType: 'application/json',
            success: function (res) {
                closeModal();
                closeCrewBuilder();
                showModal({
                    title: 'Успешно',
                    message: res.message || 'Экипаж успешно сохранен',
                    type: 'success',
                    showCancel: false,
                    onConfirm: function () { window.location.reload(); }
                });
            },
            error: function (xhr) {
                closeModal();
                if (xhr.status === 409 && xhr.responseJSON?.status === 'conflict') {
                    const conflictData = xhr.responseJSON;
                    if (conflictData.can_override) {
                        showConflictModal(
                            conflictData,
                            function onConfirmOverride() {
                                submitCrewForm(true);
                            },
                            function onCancel() {
                                // Оставляем модальное окно сборщика открытым для возможности замены сотрудника
                            }
                        );
                        return;
                    }
                }
                const err = xhr.responseJSON?.error || (xhr.responseJSON?.errors ? xhr.responseJSON.errors.join('<br>') : 'Ошибка сохранения экипажа');
                showModal({
                    title: 'Ошибка',
                    message: err,
                    type: 'error',
                    showCancel: false
                });
            }
        });
    }

    $(document).on('click', '#cbSubmitBtn', function () {
        submitCrewForm(false);
    });

    // ========================================================
    // ПАКЕТНАЯ ЗАМЕНА БОРТА ВС (BATCH AIRCRAFT SWAP)
    // ========================================================
    function openBatchSwapModal(defaultMpdId, defaultStart, defaultEnd) {
        $('#batchSwapForm')[0].reset();
        $('#bsMpdSelect').val(defaultMpdId || '');
        $('#bsStartDate').val(defaultStart || new Date().toISOString().split('T')[0]);
        $('#bsEndDate').val(defaultEnd || new Date().toISOString().split('T')[0]);

        updateBatchSwapAircraftOptions(defaultMpdId);

        $('#batchSwapOverlay').show();
        $('#batchSwapModal').show();
    }

    function closeBatchSwapModal() {
        $('#batchSwapOverlay').hide();
        $('#batchSwapModal').hide();
    }

    function updateBatchSwapAircraftOptions(mpdId, startDate, endDate) {
        const $oldGroup = $('#bsOldAircraftOptGroup');
        const $newGroup = $('#bsNewAircraftOptGroup');
        const prevOldVal = $('#bsOldAircraftSelect').val();
        const prevNewVal = $('#bsNewAircraftSelect').val();

        $oldGroup.empty();
        $newGroup.empty();

        const sDate = startDate || $('#bsStartDate').val() || new Date().toISOString().split('T')[0];
        const eDate = endDate || $('#bsEndDate').val() || sDate;
        const currentMpdId = mpdId || $('#bsMpdSelect').val();

        const allAircraft = window.ALL_AIRCRAFT || [];
        const activeGroup = [];
        const historicalGroup = [];
        const otherGroup = [];

        allAircraft.forEach(ac => {
            const status = getAircraftBasingStatus(ac.id, currentMpdId, sDate, eDate);
            const typeStr = ac.type ? ` (${ac.type})` : '';

            if (status.group === 'active') {
                activeGroup.push({ ac, status, typeStr });
            } else if (status.group === 'historical') {
                historicalGroup.push({ ac, status, typeStr });
            } else {
                otherGroup.push({ ac, status, typeStr });
            }
        });

        // Заполняем группы
        const addOptionsToSelect = ($target, items) => {
            items.forEach(item => {
                const label = `✈ ${item.ac.reg}${item.typeStr} ${item.status.label}`;
                $target.append(`<option value="${item.ac.id}">${label}</option>`);
            });
        };

        if (activeGroup.length > 0) {
            $oldGroup.append('<option disabled>── ✈ Базируются в выбранные даты ──</option>');
            addOptionsToSelect($oldGroup, activeGroup);
            $newGroup.append('<option disabled>── ✈ Базируются в выбранные даты ──</option>');
            addOptionsToSelect($newGroup, activeGroup);
        }

        if (historicalGroup.length > 0) {
            $oldGroup.append('<option disabled>── 🕒 Были на МПД в другие даты месяца ──</option>');
            addOptionsToSelect($oldGroup, historicalGroup);
            $newGroup.append('<option disabled>── 🕒 Были на МПД в другие даты месяца ──</option>');
            addOptionsToSelect($newGroup, historicalGroup);
        }

        if (otherGroup.length > 0) {
            $oldGroup.append('<option disabled>── Другие ВС авиакомпании ──</option>');
            addOptionsToSelect($oldGroup, otherGroup);
            $newGroup.append('<option disabled>── Другие ВС авиакомпании ──</option>');
            addOptionsToSelect($newGroup, otherGroup);
        }

        if (prevOldVal) $('#bsOldAircraftSelect').val(prevOldVal);
        if (prevNewVal) $('#bsNewAircraftSelect').val(prevNewVal);
    }

    $(document).on('click', '#openBatchSwapModalBtn', function (e) {
        e.preventDefault();
        let defaultMpdId = '';
        let defaultStart = '';
        let defaultEnd = '';

        if (selectedCells.length > 0) {
            defaultMpdId = $(selectedCells[0]).data('mpd-id');
            const dates = selectedCells.map(cell => $(cell).data('date')).sort();
            defaultStart = dates[0];
            defaultEnd = dates[dates.length - 1];
        } else {
            const today = new Date().toISOString().split('T')[0];
            defaultStart = today;
            defaultEnd = today;
        }

        openBatchSwapModal(defaultMpdId, defaultStart, defaultEnd);
    });

    $(document).on('click', '#closeBatchSwapCross, #bsCancelBtn, #batchSwapOverlay', function () {
        closeBatchSwapModal();
    });

    $('#bsMpdSelect').on('change', function () {
        updateBatchSwapAircraftOptions($(this).val(), $('#bsStartDate').val(), $('#bsEndDate').val());
    });

    $('#bsStartDate').on('change', function () {
        const startDate = $(this).val();
        let endDate = $('#bsEndDate').val();
        if (endDate && endDate < startDate) {
            $('#bsEndDate').val(startDate);
            endDate = startDate;
        }
        updateBatchSwapAircraftOptions($('#bsMpdSelect').val(), startDate, endDate);
    });

    $('#bsEndDate').on('change', function () {
        const endDate = $(this).val();
        const startDate = $('#bsStartDate').val();
        updateBatchSwapAircraftOptions($('#bsMpdSelect').val(), startDate, endDate);
    });

    $(document).on('click', '#bsSubmitBtn', function () {
        const mpdId = $('#bsMpdSelect').val();
        const startDate = $('#bsStartDate').val();
        const endDate = $('#bsEndDate').val();
        const oldAircraft = $('#bsOldAircraftSelect').val();
        const newAircraft = $('#bsNewAircraftSelect').val();

        if (!mpdId || !startDate || !endDate) {
            showModal({
                title: 'Не все поля заполнены',
                message: 'Выберите МПД и укажите диапазон дат',
                type: 'warning',
                showCancel: false
            });
            return;
        }

        if (startDate > endDate) {
            showModal({
                title: 'Ошибка диапазона дат',
                message: 'Дата начала не может быть позже даты окончания',
                type: 'warning',
                showCancel: false
            });
            return;
        }

        const oldAcText = $('#bsOldAircraftSelect option:selected').text();
        const newAcText = $('#bsNewAircraftSelect option:selected').text();
        const mpdText = $('#bsMpdSelect option:selected').text();

        showModal({
            title: 'Подтверждение замены борта',
            message: `Вы действительно хотите выполнить замену борта:<br><strong>${oldAcText}</strong> → <strong>${newAcText}</strong><br>на МПД «<strong>${mpdText}</strong>» в период с <strong>${startDate}</strong> по <strong>${endDate}</strong>?`,
            type: 'warning',
            showCancel: true,
            confirmText: 'Да, выполнить замену',
            cancelText: 'Отмена',
            onConfirm: function () {
                showModal({
                    title: 'Выполнение операции',
                    message: 'Пакетная замена борта в экипажах...',
                    type: 'info',
                    showCancel: false,
                    showConfirm: false
                });

                $.ajax({
                    url: '/flight/api/crew/batch-swap-aircraft/',
                    method: 'POST',
                    headers: {'X-CSRFToken': getCookie('csrftoken')},
                    data: JSON.stringify({
                        mpd_id: parseInt(mpdId),
                        start_date: startDate,
                        end_date: endDate,
                        old_aircraft_id: oldAircraft,
                        new_aircraft_id: newAircraft
                    }),
                    contentType: 'application/json',
                    success: function (res) {
                        closeModal();
                        closeBatchSwapModal();
                        showModal({
                            title: 'Успешно',
                            message: res.message || 'Замена борта выполнена',
                            type: 'success',
                            showCancel: false,
                            onConfirm: function () { window.location.reload(); }
                        });
                    },
                    error: function (xhr) {
                        closeModal();
                        const err = xhr.responseJSON?.error || (xhr.responseJSON?.errors ? xhr.responseJSON.errors.join('<br>') : 'Ошибка выполнения замены борта');
                        showModal({
                            title: 'Ошибка',
                            message: err,
                            type: 'error',
                            showCancel: false
                        });
                    }
                });
            }
        });
    });

    // Селектор тем
    $('#themeSelector').on('change', function () {
        const theme = $(this).val();
        $('body').removeClass('theme-neutral theme-classic theme-corporate').addClass(theme);
        localStorage.setItem('flight_planning_theme', theme);
    });

    const savedTheme = localStorage.getItem('flight_planning_theme');
    if (savedTheme) {
        $('#themeSelector').val(savedTheme).trigger('change');
    }

    // ========================================================
    // ФИКСАЦИЯ СОСТОЯНИЯ / СОЗДАНИЕ ДОКУМЕНТА РАССТАНОВКИ
    // ========================================================
    function openSaveStateModal() {
        $('#docReasonError').hide();
        $('#saveStateDocOverlay').show();
        $('#saveStateDocModal').show();
    }

    function closeSaveStateModal() {
        $('#saveStateDocOverlay').hide();
        $('#saveStateDocModal').hide();
    }

    $('#openSaveStateModalBtn, #bannerSaveStateBtn').on('click', function () {
        openSaveStateModal();
    });

    $('#closeSaveStateDocCross, #saveStateDocCancelBtn, #saveStateDocOverlay').on('click', function () {
        closeSaveStateModal();
    });

    $('#saveStateDocSubmitBtn').on('click', function () {
        const reason = $('#docReasonInput').val().trim();
        const urlParams = new URLSearchParams(window.location.search);
        const now = new Date();
        const year = urlParams.get('year') || now.getFullYear();
        const month = urlParams.get('month') || (now.getMonth() + 1);

        if ($('#docReasonInput').prev().find('.text-danger').length > 0 && !reason) {
            $('#docReasonError').show();
            $('#docReasonInput').focus();
            return;
        }

        $('#docReasonError').hide();
        $('#saveStateDocSubmitBtn').prop('disabled', true).html('<i class="bx bx-loader-alt bx-spin me-1"></i> Сохранение...');

        $.ajax({
            url: '/flight/documents/create/',
            method: 'POST',
            headers: {'X-CSRFToken': getCookie('csrftoken')},
            data: {
                year: year,
                month: month,
                reason: reason
            },
            success: function (res) {
                closeSaveStateModal();
                showModal({
                    title: 'Документ сформирован!',
                    message: res.message || 'Документ успешно сформирован и отправлен на утверждение.',
                    type: 'success',
                    showCancel: false,
                    onConfirm: function () {
                        if (res.redirect_url) {
                            window.location.href = res.redirect_url;
                        } else {
                            window.location.reload();
                        }
                    }
                });
            },
            error: function (xhr) {
                $('#saveStateDocSubmitBtn').prop('disabled', false).html('<i class="bx bx-check-double me-1"></i> Зафиксировать и отправить на утверждение');
                const err = xhr.responseJSON?.error || 'Ошибка при формировании документа расстановки.';
                showModal({
                    title: 'Ошибка',
                    message: err,
                    type: 'error',
                    showCancel: false
                });
            }
        });
    });

    // ========================================================
    // АВТОПРОКРУТКА И ЦЕНТРИРОВАНИЕ НА ТЕКУЩИЙ ДЕНЬ (СЕГОДНЯ)
    // ========================================================
    function scrollToToday(smooth = true) {
        const $wrapper = $('#planningTableWrapper');
        const $todayTh = $('th.today-column-header');

        if ($wrapper.length && $todayTh.length) {
            const wrapperWidth = $wrapper.width();
            const $mpdTh = $('th:first-child');
            const mpdWidth = $mpdTh.outerWidth() || 180;

            const todayOffsetLeft = $todayTh[0].offsetLeft;
            const todayWidth = $todayTh.outerWidth() || 120;

            const visibleAreaWidth = wrapperWidth - mpdWidth;
            const targetScrollLeft = todayOffsetLeft - mpdWidth - (visibleAreaWidth / 2) + (todayWidth / 2);
            const scrollValue = Math.max(0, targetScrollLeft);

            if (smooth) {
                $wrapper.stop().animate({ scrollLeft: scrollValue }, 400);
            } else {
                $wrapper.scrollLeft(scrollValue);
            }
        }
    }

    if ($('th.today-column-header').length) {
        setTimeout(function () {
            scrollToToday(false);
        }, 150);
    }

    $('#todayNavBtn').on('click', function (e) {
        if ($('th.today-column-header').length) {
            e.preventDefault();
            scrollToToday(true);
        }
    });

    // ========================================================
    // ДЕТАЛЬНЫЙ ПРОСМОТР ПЕРИОДИЧЕСКИХ МЕРОПРИЯТИЙ СОТРУДНИКА
    // ========================================================
    function openPilotCheckDetails(pilotId) {
        if (!pilotId) return;

        const pilotObj = window.ALL_PILOTS ? window.ALL_PILOTS.find(p => p.id == pilotId) : null;
        const pilotName = pilotObj ? pilotObj.name : `Сотрудник #${pilotId}`;

        $('#pcdPilotNameTitle').html(`<i class="bx bx-check-shield me-2"></i> Мероприятия сотрудника: ${pilotName}`);
        $('#pcdChecksTableBody').html('<tr><td colspan="5" class="text-center py-3"><i class="bx bx-loader-alt bx-spin"></i> Загрузка данных мероприятий...</td></tr>');
        $('#pcdOverallStatusBanner').hide();

        $('#pilotCheckDetailsOverlay').show();
        $('#pilotCheckDetailsModal').show();

        $.ajax({
            url: `/flight/api/pilot-checks/${pilotId}/`,
            method: 'GET',
            success: function (res) {
                if (res.status === 'success' && res.check_status) {
                    const cs = res.check_status;
                    let bannerHtml = '';
                    if (cs.has_expired || cs.has_missing) {
                        bannerHtml = `<div class="alert alert-danger py-2 mb-3"><i class="bx bx-error-circle me-1"></i> <strong>Внимание:</strong> Имеются просроченные или непройденные мероприятия: ${cs.summary_text}</div>`;
                    } else if (cs.has_warning) {
                        bannerHtml = `<div class="alert alert-warning py-2 mb-3"><i class="bx bx-time-five me-1"></i> <strong>Предупреждение:</strong> Имеются мероприятия, истекающие в ближайшие 30 дней: ${cs.summary_text}</div>`;
                    } else {
                        bannerHtml = `<div class="alert alert-success py-2 mb-3"><i class="bx bx-check-circle me-1"></i> Все обязательные периодические мероприятия в норме и действительны.</div>`;
                    }
                    $('#pcdOverallStatusBanner').html(bannerHtml).show();

                    const checksList = cs.details || cs.checks || [];
                    let rowsHtml = '';
                    if (checksList.length > 0) {
                        checksList.forEach(c => {
                            const daysLeft = (c.days_remaining !== undefined && c.days_remaining !== null) ? c.days_remaining : c.days_left;
                            let statusBadge = '';
                            if (c.status === 'expired') {
                                const overdueDays = (daysLeft !== null && daysLeft !== undefined) ? Math.abs(daysLeft) + ' дн. назад' : '';
                                statusBadge = `<span class="badge bg-danger">Просрочено (${overdueDays})</span>`;
                            } else if (c.status === 'warning') {
                                statusBadge = `<span class="badge bg-warning text-dark">Истекает (${daysLeft} дн.)</span>`;
                            } else if (c.status === 'valid') {
                                statusBadge = `<span class="badge bg-success">Действует (${daysLeft} дн.)</span>`;
                            } else {
                                statusBadge = `<span class="badge bg-secondary">Не пройдено / Нет данных</span>`;
                            }

                            const checkTitle = c.check_name || c.check_type_name || 'Периодическое мероприятие';
                            const startDateStr = c.start_date || '—';
                            const endDateStr = c.end_date || '—';
                            const acStr = c.aircraft_type_name || '* (Все ВС)';
                            const docInfo = c.document_number ? `<br><small class="text-muted">№ ${c.document_number}</small>` : '';

                            rowsHtml += `
                                <tr>
                                    <td><strong>${checkTitle}</strong>${docInfo}</td>
                                    <td><span class="badge bg-light text-dark border">${acStr}</span></td>
                                    <td>${startDateStr}</td>
                                    <td><strong>${endDateStr}</strong></td>
                                    <td>${statusBadge}</td>
                                </tr>
                            `;
                        });
                    } else {
                        rowsHtml = '<tr><td colspan="5" class="text-center text-muted py-3">Нет зарегистрированных мероприятий</td></tr>';
                    }
                    $('#pcdChecksTableBody').html(rowsHtml);
                    $('#pcdOpenJournalLink').attr('href', `/flight/checks/?employee_id=${pilotId}`);
                }
            },
            error: function () {
                $('#pcdChecksTableBody').html('<tr><td colspan="5" class="text-center text-danger py-3">Не удалось загрузить данные о мероприятиях</td></tr>');
            }
        });
    }

    $(document).on('click', '.check-status-icon', function (e) {
        e.stopPropagation();
        const pilotId = $(this).data('pilot-id');
        openPilotCheckDetails(pilotId);
    });

    $('#closePilotCheckDetailsCross, #closePilotCheckDetailsBtn, #pilotCheckDetailsOverlay').on('click', function () {
        $('#pilotCheckDetailsOverlay').hide();
        $('#pilotCheckDetailsModal').hide();
    });
});


