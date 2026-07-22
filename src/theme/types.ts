export interface Theme {
  colors: {
    bg: {
      app: string;
      sidebar: string;
      modal: string;
    };
    border: {
      default: string;
      active: string;
      muted: string;
    };
    text: {
      ethereal: string;
      muted: string;
      emerald: string;
      warning: string;
      error: string;
    };
    shadow: {
      ascii: string;
    };
    diff: {
      addBg: string;
      addWordBg: string;
      removeBg: string;
      removeWordBg: string;
    };
    logo: string[];
  };
}
