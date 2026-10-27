/*
 * Тёмная тема Blockly, согласованная с resources/styles/dark.qss.
 * Акцент #5865f2, фон #1e1f22, панели #232428 / #2b2d31, границы #3a3d43.
 */
'use strict';

const clickitDark = Blockly.Theme.defineTheme('clickitDark', {
  base: Blockly.Themes.Classic,
  componentStyles: {
    workspaceBackgroundColour: '#1e1f22',
    toolboxBackgroundColour: '#232428',
    toolboxForegroundColour: '#e6e6e6',
    flyoutBackgroundColour: '#2b2d31',
    flyoutForegroundColour: '#e6e6e6',
    flyoutOpacity: 1,
    scrollbarColour: '#3a3d43',
    scrollbarOpacity: 0.8,
    insertionMarkerColour: '#5865f2',
    insertionMarkerOpacity: 0.4,
    markerColour: '#5865f2',
    cursorColour: '#5865f2',
  },
  fontStyle: {
    family: '"Segoe UI", "Inter", sans-serif',
    weight: 'normal',
    size: 11,
  },
  startHats: false,
});
