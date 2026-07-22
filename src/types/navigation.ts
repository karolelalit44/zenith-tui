export type Screen =
  | 'welcome'
  | 'chat'
  | 'settings'
  | 'settings.theme'
  | 'settings.account'
  | 'settings.plugins';

export interface NavigationState {
  currentScreen: Screen;
  history: Screen[];
}

export interface NavigationContextType {
  state: NavigationState;
  navigate: (screen: Screen) => void;
  goBack: () => void;
  canGoBack: boolean;
}
