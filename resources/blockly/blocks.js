/*
 * Кастомные блоки ClicKit. Один блок = один IR-узел.
 * Определения декларативные: транслятор в IR живёт в bridge/blockly_ir.py.
 */
'use strict';

Blockly.common.defineBlocksWithJsonArray([
  {
    type: 'ck_click',
    message0: 'клик в x: %1 y: %2 кнопкой %3',
    args0: [
      {
        type: 'field_number', name: 'X', value: 400,
        min: -32768, max: 32767, precision: 1,
      },
      {
        type: 'field_number', name: 'Y', value: 300,
        min: -32768, max: 32767, precision: 1,
      },
      {
        type: 'field_dropdown', name: 'BUTTON',
        options: [['левой', 'left'], ['правой', 'right'], ['средней', 'middle']],
      },
    ],
    previousStatement: null,
    nextStatement: null,
    colour: '#4C97FF',
    tooltip: 'Кликнуть указанной кнопкой мыши в точку экрана.',
  },
  {
    type: 'ck_double_click',
    message0: 'двойной клик в x: %1 y: %2 кнопкой %3',
    args0: [
      {
        type: 'field_number', name: 'X', value: 400,
        min: -32768, max: 32767, precision: 1,
      },
      {
        type: 'field_number', name: 'Y', value: 300,
        min: -32768, max: 32767, precision: 1,
      },
      {
        type: 'field_dropdown', name: 'BUTTON',
        options: [['левой', 'left'], ['правой', 'right'], ['средней', 'middle']],
      },
    ],
    previousStatement: null,
    nextStatement: null,
    colour: '#4C97FF',
    tooltip: 'Два быстрых клика в точку экрана.',
  },
  {
    type: 'ck_move',
    message0: 'переместить курсор в x: %1 y: %2 за %3 сек',
    args0: [
      {
        type: 'field_number', name: 'X', value: 400,
        min: -32768, max: 32767, precision: 1,
      },
      {
        type: 'field_number', name: 'Y', value: 300,
        min: -32768, max: 32767, precision: 1,
      },
      {
        type: 'field_number', name: 'DURATION', value: 0.2,
        min: 0, max: 60, precision: 0.1,
      },
    ],
    previousStatement: null,
    nextStatement: null,
    colour: '#4C97FF',
    tooltip: 'Плавно переместить курсор в точку за указанное время.',
  },
  {
    type: 'ck_drag',
    message0: 'перетащить в x: %1 y: %2 за %3 сек кнопкой %4',
    args0: [
      {
        type: 'field_number', name: 'X', value: 400,
        min: -32768, max: 32767, precision: 1,
      },
      {
        type: 'field_number', name: 'Y', value: 300,
        min: -32768, max: 32767, precision: 1,
      },
      {
        type: 'field_number', name: 'DURATION', value: 0.5,
        min: 0, max: 60, precision: 0.1,
      },
      {
        type: 'field_dropdown', name: 'BUTTON',
        options: [['левой', 'left'], ['правой', 'right'], ['средней', 'middle']],
      },
    ],
    previousStatement: null,
    nextStatement: null,
    colour: '#4C97FF',
    tooltip: 'Зажать кнопку мыши и перетащить курсор в точку.',
  },
  {
    type: 'ck_scroll',
    message0: 'прокрутить на %1',
    args0: [
      {
        type: 'field_number', name: 'AMOUNT', value: 3,
        min: -100, max: 100, precision: 1,
      },
    ],
    previousStatement: null,
    nextStatement: null,
    colour: '#4C97FF',
    tooltip: 'Прокрутить колесо мыши: положительное число — вверх, отрицательное — вниз.',
  },
  {
    type: 'ck_scroll_at',
    message0: 'прокрутить на %1 в точке x: %2 y: %3',
    args0: [
      {
        type: 'field_number', name: 'AMOUNT', value: 3,
        min: -100, max: 100, precision: 1,
      },
      {
        type: 'field_number', name: 'X', value: 400,
        min: -32768, max: 32767, precision: 1,
      },
      {
        type: 'field_number', name: 'Y', value: 300,
        min: -32768, max: 32767, precision: 1,
      },
    ],
    previousStatement: null,
    nextStatement: null,
    colour: '#4C97FF',
    tooltip: 'Прокрутить колесо мыши в указанной точке экрана.',
  },
  {
    type: 'ck_key',
    message0: 'нажать клавиши %1',
    args0: [
      {type: 'field_input', name: 'KEYS', text: ''},
    ],
    previousStatement: null,
    nextStatement: null,
    colour: '#9966FF',
    tooltip: 'Комбинация клавиш: например, ctrl+s, enter, f5. Можно одну клавишу.',
  },
  {
    type: 'ck_delay',
    message0: 'пауза %1 сек',
    args0: [
      {
        type: 'field_number', name: 'SECONDS', value: 0.5,
        min: 0, max: 3600, precision: 0.1,
      },
    ],
    previousStatement: null,
    nextStatement: null,
    colour: '#FFAB19',
    tooltip: 'Подождать указанное время. Пауза прерывается кнопкой «Стоп» (F6).',
  },
  {
    type: 'ck_loop',
    message0: 'повторить %1 раз',
    args0: [
      {
        type: 'field_number', name: 'TIMES', value: 3,
        min: 1, max: 1000000, precision: 1,
      },
    ],
    message1: 'выполнить %1',
    args1: [
      {type: 'input_statement', name: 'DO'},
    ],
    previousStatement: null,
    nextStatement: null,
    colour: '#59C059',
    tooltip: 'Повторить блоки внутри указанное число раз.',
  },
  {
    type: 'ck_loop_forever',
    message0: 'повторять бесконечно',
    message1: 'выполнить %1',
    args1: [
      {type: 'input_statement', name: 'DO'},
    ],
    previousStatement: null,
    nextStatement: null,
    colour: '#59C059',
    tooltip: 'Повторять блоки внутри до нажатия «Стоп» (F6).',
  },
]);
