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

export const themes: Record<string, Theme> = {
  deep_forest: {
    colors: {
      bg: { app: '#0D1A15', sidebar: '#142921', modal: '#1A3329' },
      border: { default: '#244738', active: '#50C878', muted: '#1A3329' },
      text: { ethereal: '#F5FFFA', muted: '#8FBC8F', emerald: '#50C878', warning: '#DAA520', error: '#FF6B6B' },
      shadow: { ascii: '#08120E' },
      diff: { addBg: '#112B1C', addWordBg: '#1B4D31', removeBg: '#2B1111', removeWordBg: '#4D1B1B' },
      logo: ['#F5FFFA', '#D1E8D1', '#A3CBA3', '#7CA87C', '#558055', '#2E522E']
    }
  },
  synthwave: {
    colors: {
      bg: { app: '#1A0E2A', sidebar: '#25153A', modal: '#2E1949' },
      border: { default: '#45266D', active: '#F92A82', muted: '#2E1949' },
      text: { ethereal: '#FDF1F5', muted: '#A385C2', emerald: '#00F2FE', warning: '#F39C12', error: '#FF2A2A' },
      shadow: { ascii: '#10081C' },
      diff: { addBg: '#1B264A', addWordBg: '#154A66', removeBg: '#4A1B26', removeWordBg: '#661530' },
      logo: ['#FF66CC', '#E04DBF', '#C233B2', '#A31AA5', '#850099', '#66008C']
    }
  },
  monokai: {
    colors: {
      bg: { app: '#272822', sidebar: '#2E2F29', modal: '#34352F' },
      border: { default: '#49483E', active: '#A6E22E', muted: '#34352F' },
      text: { ethereal: '#F8F8F2', muted: '#75715E', emerald: '#A6E22E', warning: '#FD971F', error: '#F92672' },
      shadow: { ascii: '#151613' },
      diff: { addBg: '#3E4924', addWordBg: '#596934', removeBg: '#49243E', removeWordBg: '#693459' },
      logo: ['#A6E22E', '#BCE22E', '#D2E22E', '#E8E22E', '#FDE22E', '#FD971F']
    }
  },
  dracula: {
    colors: {
      bg: { app: '#282A36', sidebar: '#303240', modal: '#383A4A' },
      border: { default: '#44475A', active: '#50FA7B', muted: '#383A4A' },
      text: { ethereal: '#F8F8F2', muted: '#6272A4', emerald: '#8BE9FD', warning: '#FFB86C', error: '#FF5555' },
      shadow: { ascii: '#1E1F28' },
      diff: { addBg: '#233F39', addWordBg: '#2A5A51', removeBg: '#422735', removeWordBg: '#5A2A47' },
      logo: ['#BD93F9', '#B084F5', '#A375F1', '#9666ED', '#8957E9', '#FF79C6']
    }
  },
  aura: {
    colors: {
      bg: { app: '#15141B', sidebar: '#1B1A22', modal: '#21202A' },
      border: { default: '#3D3B4F', active: '#61FFCA', muted: '#21202A' },
      text: { ethereal: '#EDECEE', muted: '#6D6A86', emerald: '#82E2FF', warning: '#F694FF', error: '#FF6767' },
      shadow: { ascii: '#0E0D11' },
      diff: { addBg: '#1C3138', addWordBg: '#254E5A', removeBg: '#381C26', removeWordBg: '#5A2538' },
      logo: ['#61FFCA', '#6BEEF6', '#75DDFF', '#93AEFF', '#A392FF', '#A277FF']
    }
  }
};
