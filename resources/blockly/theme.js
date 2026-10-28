/*
 * Темы Blockly, согласованные с resources/styles/dark.qss и light.qss.
 * Акцент #5865f2, тёмная: фон #1e1f22, панели #232428 / #2b2d31, границы #3a3d43;
 * светлая: фон #f4f5f7, панели #ffffff / #eceef2, границы #d6d9e0.
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

const clickitLight = Blockly.Theme.defineTheme('clickitLight', {
  base: Blockly.Themes.Classic,
  componentStyles: {
    workspaceBackgroundColour: '#f4f5f7',
    toolboxBackgroundColour: '#ffffff',
    toolboxForegroundColour: '#1f2124',
    flyoutBackgroundColour: '#eceef2',
    flyoutForegroundColour: '#1f2124',
    flyoutOpacity: 1,
    scrollbarColour: '#c2c7d0',
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
