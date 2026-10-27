/*
 * Логика страницы редактора ClicKit: Blockly + тулбар + мост QWebChannel.
 * Трансляция в IR выполняется в Python (bridge/blockly_ir.py).
 */
'use strict';

(function () {
  const DEFAULT_NAME = 'Пример';

  // Подготовительный сценарий: клик → пауза → цикл 3×(движение + клик).
  const STARTER = {
    blocks: {
      languageVersion: 0,
      blocks: [
        {
          type: 'ck_click',
          id: 'starter-click',
          x: 40,
          y: 40,
          fields: {X: 400, Y: 300, BUTTON: 'left'},
          next: {
            block: {
              type: 'ck_delay',
              id: 'starter-delay',
              fields: {SECONDS: 0.5},
              next: {
                block: {
                  type: 'ck_loop',
                  id: 'starter-loop',
                  fields: {TIMES: 3},
                  inputs: {
                    DO: {
                      block: {
                        type: 'ck_move',
                        id: 'starter-move',
                        fields: {X: 600, Y: 300, DURATION: 0.2},
                        next: {
                          block: {
                            type: 'ck_click',
                            id: 'starter-click-2',
                            fields: {X: 600, Y: 300, BUTTON: 'left'}
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
      ]
    }
  };

  const TOOLBOX = {
    kind: 'categoryToolbox',
    contents: [
      {
        kind: 'category',
        name: 'Мышь',
        colour: '#4C97FF',
        contents: [
          {kind: 'block', type: 'ck_click'},
          {kind: 'block', type: 'ck_double_click'},
          {kind: 'block', type: 'ck_move'},
          {kind: 'block', type: 'ck_drag'},
          {kind: 'block', type: 'ck_scroll'},
          {kind: 'block', type: 'ck_scroll_at'}
        ]
      },
      {
        kind: 'category',
        name: 'Клавиатура',
        colour: '#9966FF',
        contents: [
          {kind: 'block', type: 'ck_key'}
        ]
      },
      {
        kind: 'category',
        name: 'Задержки',
        colour: '#FFAB19',
        contents: [
          {kind: 'block', type: 'ck_delay'}
        ]
      },
      {
        kind: 'category',
        name: 'Циклы',
        colour: '#59C059',
        contents: [
          {kind: 'block', type: 'ck_loop'},
          {kind: 'block', type: 'ck_loop_forever'}
        ]
      }
    ]
  };

  let workspace = null;
  let bridge = null;
  let running = false;
  let dirty = false;
  let lastHighlighted = null;
  let modalResolve = null;

  const nameInput = document.getElementById('name');
  const dirtyMarker = document.getElementById('dirty');
  const statusText = document.getElementById('status');
  const stepText = document.getElementById('step');
  const runButton = document.getElementById('btn-run');
  const stopButton = document.getElementById('btn-stop');
  const saveButton = document.getElementById('btn-save');
  const openButton = document.getElementById('btn-open');
  const newButton = document.getElementById('btn-new');
  const undoButton = document.getElementById('btn-undo');
  const redoButton = document.getElementById('btn-redo');

  function setStatus(text, isError) {
    statusText.textContent = text || '';
    statusText.classList.toggle('error', Boolean(isError));
  }

  function getName() {
    const value = nameInput.value.trim();
    return value || 'Сценарий';
  }

  function updateTitle() {
    document.title = (dirty ? '• ' : '') + getName() + ' — ClicKit';
  }

  function setDirty(value) {
    dirty = Boolean(value);
    dirtyMarker.classList.toggle('visible', dirty);
    updateTitle();
  }

  function serializeWorkspace() {
    return JSON.stringify(Blockly.serialization.workspaces.save(workspace));
  }

  function clearWarnings() {
    if (!workspace) {
      return;
    }
    workspace.getAllBlocks(false).forEach(function (block) {
      if (block.warning) {
        block.setWarningText(null);
      }
    });
  }

  function clearHighlight() {
    if (lastHighlighted) {
      try {
        lastHighlighted.removeClass('ck-running');
      } catch (error) {
        // блок мог быть удалён во время выполнения
      }
      lastHighlighted = null;
    }
    if (workspace) {
      try {
        workspace.highlightBlock(null);
      } catch (error) {
        // подсветка могла быть уже снята
      }
    }
  }

  function highlightBlock(id) {
    if (!workspace || !id) {
      return;
    }
    const block = workspace.getBlockById(id);
    if (!block) {
      return;
    }
    if (lastHighlighted && lastHighlighted !== block) {
      try {
        lastHighlighted.removeClass('ck-running');
      } catch (error) {
        // предыдущий блок удалён
      }
    }
    block.addClass('ck-running');
    lastHighlighted = block;
    try {
      workspace.highlightBlock(id);
    } catch (error) {
      // визуальная подсветка не критична для выполнения
    }
  }

  function updateUndoRedo() {
    if (!workspace) {
      return;
    }
    try {
      undoButton.disabled = workspace.getUndoStack().length === 0;
      redoButton.disabled = workspace.getRedoStack().length === 0;
    } catch (error) {
      // API стека недоступен — кнопки остаются активными
    }
  }

  function applyRunningState(value) {
    running = Boolean(value);
    runButton.disabled = running;
    stopButton.disabled = !running;
  }

  function onWorkspaceChange(event) {
    if (!event || event.isUiEvent || event.type === Blockly.Events.VIEWPORT_CHANGE) {
      return;
    }
    clearWarnings();
    setDirty(true);
    updateUndoRedo();
  }

  function onScenarioLoaded(name, workspaceJson) {
    let state;
    try {
      state = JSON.parse(workspaceJson);
    } catch (error) {
      setStatus('Не удалось восстановить блоки из файла', true);
      return;
    }
    Blockly.Events.disable();
    try {
      Blockly.serialization.workspaces.load(state, workspace);
      workspace.cleanUp();
    } finally {
      Blockly.Events.enable();
    }
    clearWarnings();
    clearHighlight();
    nameInput.value = name || 'Сценарий';
    setDirty(false);
    stepText.textContent = '';
    updateUndoRedo();
    setStatus('Сценарий открыт', false);
  }

  function onSaved(path, name) {
    if (name) {
      nameInput.value = name;
    }
    setDirty(false);
    setStatus('Сохранено: ' + path, false);
  }

  function onRunFinished(reason, message) {
    applyRunningState(false);
    setStatus(message, reason === 'error');
    stepText.textContent = '';
    if (reason === 'completed') {
      window.setTimeout(clearHighlight, 800);
    } else {
      clearHighlight();
    }
  }

  function onRunningChanged(value) {
    applyRunningState(value);
    if (value) {
      clearWarnings();
      stepText.textContent = '';
    }
  }

  function onIssues(payload) {
    let issues;
    try {
      issues = JSON.parse(payload);
    } catch (error) {
      setStatus('Не удалось разобрать список ошибок', true);
      return;
    }
    clearWarnings();
    let firstBlock = null;
    issues.forEach(function (issue) {
      if (!issue || !issue.block_id) {
        return;
      }
      const block = workspace.getBlockById(issue.block_id);
      if (!block) {
        return;
      }
      block.setWarningText(issue.message);
      if (!firstBlock) {
        firstBlock = block;
      }
    });
    if (firstBlock) {
      try {
        workspace.centerOnBlock(firstBlock.id, true);
      } catch (error) {
        // центрирование не критично
      }
    }
  }

  function requestRun() {
    if (!bridge) {
      setStatus('Мост с приложением недоступен', true);
      return;
    }
    if (running) {
      return;
    }
    setStatus('Проверяю сценарий…', false);
    bridge.run(getName(), serializeWorkspace());
  }

  function requestSave() {
    if (!bridge) {
      setStatus('Мост с приложением недоступен', true);
      return;
    }
    bridge.save(getName(), serializeWorkspace());
  }

  function requestOpen() {
    if (!bridge) {
      setStatus('Мост с приложением недоступен', true);
      return;
    }
    bridge.open();
  }

  function newScenario() {
    Blockly.Events.disable();
    try {
      workspace.clear();
    } finally {
      Blockly.Events.enable();
    }
    if (typeof workspace.clearUndo === 'function') {
      workspace.clearUndo();
    }
    clearWarnings();
    clearHighlight();
    nameInput.value = 'Новый сценарий';
    setDirty(false);
    stepText.textContent = '';
    updateUndoRedo();
    if (bridge) {
      bridge.new_document();
    }
    setStatus('Новый сценарий', false);
  }

  function closeModal(value) {
    document.getElementById('modal').classList.add('hidden');
    if (modalResolve) {
      const resolve = modalResolve;
      modalResolve = null;
      resolve(value);
    }
  }

  function askConfirm(message) {
    document.getElementById('modal-text').textContent = message;
    document.getElementById('modal').classList.remove('hidden');
    return new Promise(function (resolve) {
      modalResolve = resolve;
    });
  }

  function withDiscardCheck(action) {
    if (!dirty) {
      action();
      return;
    }
    askConfirm('Изменения не сохранены. Продолжить без сохранения?').then(
      function (ok) {
        if (ok) {
          action();
        }
      }
    );
  }

  function initChannel() {
    if (typeof qt === 'undefined' || !qt.webChannelTransport) {
      setStatus('Мост с приложением недоступен — запустите редактор через ClicKit', true);
      return;
    }
    new QWebChannel(qt.webChannelTransport, function (channel) {
      bridge = channel.objects.bridge;
      if (!bridge) {
        setStatus('Мост с приложением недоступен', true);
        return;
      }
      bridge.scenario_loaded.connect(onScenarioLoaded);
      bridge.node_started.connect(highlightBlock);
      bridge.step_done.connect(function (count) {
        stepText.textContent = 'шаг ' + count;
      });
      bridge.run_finished.connect(onRunFinished);
      bridge.issues_found.connect(onIssues);
      bridge.status_changed.connect(setStatus);
      bridge.document_saved.connect(onSaved);
      bridge.running_changed.connect(onRunningChanged);
      window.__ckChannelReady = true;
      bridge.ready();
    });
  }

  function bindToolbar() {
    runButton.addEventListener('click', requestRun);
    stopButton.addEventListener('click', function () {
      if (bridge) {
        bridge.stop();
      }
    });
    saveButton.addEventListener('click', requestSave);
    openButton.addEventListener('click', function () {
      withDiscardCheck(requestOpen);
    });
    newButton.addEventListener('click', function () {
      withDiscardCheck(newScenario);
    });
    undoButton.addEventListener('click', function () {
      workspace.undo(false);
    });
    redoButton.addEventListener('click', function () {
      workspace.redo(false);
    });
    nameInput.addEventListener('input', function () {
      setDirty(true);
    });

    document.getElementById('modal-ok').addEventListener('click', function () {
      closeModal(true);
    });
    document.getElementById('modal-cancel').addEventListener('click', function () {
      closeModal(false);
    });
    document.getElementById('modal').addEventListener('click', function (event) {
      if (event.target.id === 'modal') {
        closeModal(false);
      }
    });

    document.addEventListener(
      'keydown',
      function (event) {
        const ctrl = event.ctrlKey || event.metaKey;
        if (!ctrl) {
          return;
        }
        const key = (event.key || '').toLowerCase();
        if (key === 's') {
          event.preventDefault();
          requestSave();
        } else if (key === 'o') {
          event.preventDefault();
          withDiscardCheck(requestOpen);
        }
      },
      true
    );
  }

  function init() {
    try {
      workspace = Blockly.inject('blocklyDiv', {
        toolbox: TOOLBOX,
        theme: clickitDark,
        renderer: 'zelos',
        media: 'media/',
        grid: {spacing: 24, length: 2, colour: '#3a3d43', snap: true},
        zoom: {
          controls: true,
          wheel: true,
          startScale: 0.9,
          maxScale: 2,
          minScale: 0.4,
          scaleSpeed: 1.2,
          pinch: true
        },
        move: {scrollbars: true, drag: true, wheel: true},
        trashcan: true,
        sounds: false,
        comments: false,
        collapse: true
      });
      Blockly.serialization.workspaces.load(STARTER, workspace);
      workspace.cleanUp();
      workspace.addChangeListener(onWorkspaceChange);
      bindToolbar();
      initChannel();
      nameInput.value = DEFAULT_NAME;
      setDirty(false);
      updateUndoRedo();

      window.editorApi = {
        exportForRun: function () {
          if (!workspace) {
            return null;
          }
          return JSON.stringify({
            name: getName(),
            workspace: Blockly.serialization.workspaces.save(workspace)
          });
        },
        getWorkspaceStats: function () {
          return JSON.stringify({
            blocks: workspace ? workspace.getAllBlocks(false).length : 0,
            dirty: dirty,
            running: running,
            name: getName()
          });
        },
        highlightBlock: highlightBlock,
        clearHighlight: clearHighlight
      };
      window.__ckReady = true;
      setStatus('Загрузка редактора…', false);
    } catch (error) {
      window.__ckError = error && error.message ? error.message : String(error);
      setStatus('Ошибка редактора: ' + window.__ckError, true);
      if (window.console) {
        console.error(error);
      }
    }
  }

  window.addEventListener('error', function (event) {
    setStatus('Ошибка редактора: ' + event.message, true);
  });
  window.addEventListener('load', init);
})();



