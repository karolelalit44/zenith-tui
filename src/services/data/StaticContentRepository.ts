import { UI_CONTENT, UIContent } from '../../constants/uiContent';

export const getUIContent = (): UIContent => UI_CONTENT;

export const getCommands = () => UI_CONTENT.commands;

export const getAppMetadata = () => UI_CONTENT.app;

export const getStatusBarLabels = () => UI_CONTENT.statusBar;

export const getExportMetadata = () => UI_CONTENT.export;
