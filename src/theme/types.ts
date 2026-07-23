export interface Theme {
  colors: {
    bg: {
      /** App-level background (reserved for future Ink bg support) */
      app: string;
      /** Sidebar background (reserved for future Ink bg support) */
      sidebar: string;
      /** Modal background - used as fallback text color context */
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
      bright: string;
      dim: string;
    };
    status: {
      success: string;
      info: string;
      error: string;
      warning: string;
      accent: string;
    };
    diff: {
      addBg: string;
      addWordBg: string;
      addFg: string;
      removeBg: string;
      removeWordBg: string;
      removeFg: string;
    };
    code: {
      border: string;
      background: string;
      lineNum: string;
      output: string;
    };
    shadow: {
      ascii: string;
    };
    logo: string[];
  };
}
