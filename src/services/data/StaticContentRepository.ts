import { UI_CONTENT, UIContent } from '../../constants/uiContent';

export class StaticContentRepository {
  public static getUIContent(): UIContent {
    return UI_CONTENT;
  }

  public static getCommands() {
    return UI_CONTENT.commands;
  }

  public static getAppMetadata() {
    return UI_CONTENT.app;
  }

  public static getStatusBarLabels() {
    return UI_CONTENT.statusBar;
  }

  public static getExportMetadata() {
    return UI_CONTENT.export;
  }
}
