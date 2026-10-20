import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

export default class MeiLate extends Extension {
    enable() { console.log('[mei-late] enabled'); }
    disable() { console.log('[mei-late] disabled'); }
}
