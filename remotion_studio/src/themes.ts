export type VisualThemeId =
  | 'auto'
  | 'floral_rose'
  | 'fresh_mint'
  | 'flash_gold'
  | 'luxury_dark'
  | 'ribbon_sticker';

export interface VisualThemeTokens {
  id: Exclude<VisualThemeId, 'auto'>;
  brandColor: string;
  productColor: string;
  categoryColor: string;
  accentStroke: string;
  outerStroke: string;
  showFloral: boolean;
  cardBg?: string;
  cardBorder?: string;
  cardTiltDeg?: number;
  topTag?: string;
  topTagBg?: string;
  topTagColor?: string;
  pillBg: string;
  pillBorder: string;
  pillText: string;
  progressGradient: string;
  ctaBg: string;
  ctaBorder: string;
}

export const VISUAL_THEMES: Record<Exclude<VisualThemeId, 'auto'>, VisualThemeTokens> = {
  floral_rose: {
    id: 'floral_rose',
    brandColor: '#FFFFFF',
    productColor: '#38BDF8',
    categoryColor: '#FFF380',
    accentStroke: '#BE185D',
    outerStroke: '#FFFFFF',
    showFloral: true,
    pillBg: 'linear-gradient(135deg, rgba(15,23,42,0.86), rgba(6,78,59,0.88))',
    pillBorder: '2px solid rgba(52,211,153,0.85)',
    pillText: '#FFFFFF',
    progressGradient: 'linear-gradient(90deg, #FFE500 0%, #34D399 55%, #38BDF8 100%)',
    ctaBg: 'linear-gradient(90deg, #F59E0B, #EF4444)',
    ctaBorder: '2px solid #FEF08A',
  },
  fresh_mint: {
    id: 'fresh_mint',
    brandColor: '#FFFFFF',
    productColor: '#67E8F9',
    categoryColor: '#A7F3D0',
    accentStroke: '#0E7490',
    outerStroke: '#083344',
    showFloral: false,
    cardBg: 'linear-gradient(135deg, rgba(8,51,68,0.78), rgba(6,95,70,0.72))',
    cardBorder: '3px solid rgba(103,232,249,0.88)',
    topTag: '❄️ MÁT LẠNH & SẠCH SÂU',
    topTagBg: 'linear-gradient(90deg, #06B6D4, #10B981)',
    topTagColor: '#FFFFFF',
    pillBg: 'linear-gradient(135deg, rgba(8,51,68,0.9), rgba(15,118,110,0.9))',
    pillBorder: '2px solid rgba(103,232,249,0.9)',
    pillText: '#ECFEFF',
    progressGradient: 'linear-gradient(90deg, #22D3EE 0%, #34D399 60%, #A7F3D0 100%)',
    ctaBg: 'linear-gradient(90deg, #0891B2, #10B981)',
    ctaBorder: '2px solid #A5F3FC',
  },
  flash_gold: {
    id: 'flash_gold',
    brandColor: '#FFFBEB',
    productColor: '#FFE500',
    categoryColor: '#FFFFFF',
    accentStroke: '#B91C1C',
    outerStroke: '#450A0A',
    showFloral: false,
    cardBg: 'linear-gradient(135deg, rgba(153,27,27,0.88), rgba(217,119,6,0.86))',
    cardBorder: '3px solid #FDE047',
    topTag: '🔥 DEAL HỜI TIKTOK SHOP',
    topTagBg: 'linear-gradient(90deg, #FACC15, #F97316)',
    topTagColor: '#111827',
    pillBg: 'linear-gradient(135deg, rgba(127,29,29,0.92), rgba(180,83,9,0.92))',
    pillBorder: '2px solid #FACC15',
    pillText: '#FEF9C3',
    progressGradient: 'linear-gradient(90deg, #FACC15 0%, #F97316 55%, #EF4444 100%)',
    ctaBg: 'linear-gradient(90deg, #DC2626, #EA580C)',
    ctaBorder: '2px solid #FDE047',
  },
  luxury_dark: {
    id: 'luxury_dark',
    brandColor: '#FEF3C7',
    productColor: '#FBBF24',
    categoryColor: '#F8FAFC',
    accentStroke: '#1E293B',
    outerStroke: '#09090B',
    showFloral: false,
    cardBg: 'rgba(15, 23, 42, 0.84)',
    cardBorder: '2px solid rgba(251, 191, 36, 0.82)',
    topTag: '✨ REVIEW CHÂN THỰC',
    topTagBg: 'linear-gradient(90deg, #F59E0B, #FDE68A)',
    topTagColor: '#0F172A',
    pillBg: 'rgba(15, 23, 42, 0.90)',
    pillBorder: '2px solid rgba(251, 191, 36, 0.85)',
    pillText: '#FEF3C7',
    progressGradient: 'linear-gradient(90deg, #FDE68A 0%, #F59E0B 60%, #FFFFFF 100%)',
    ctaBg: 'linear-gradient(90deg, #1E293B, #B45309)',
    ctaBorder: '2px solid #FCD34D',
  },
  ribbon_sticker: {
    id: 'ribbon_sticker',
    brandColor: '#FFFFFF',
    productColor: '#FF4D6D',
    categoryColor: '#FFE500',
    accentStroke: '#1D4ED8',
    outerStroke: '#FFFFFF',
    showFloral: false,
    cardBg: 'rgba(24, 24, 27, 0.72)',
    cardBorder: '4px solid #FFFFFF',
    cardTiltDeg: -2,
    topTag: '⚡ MUST-TRY HÔM NAY',
    topTagBg: '#FF4D6D',
    topTagColor: '#FFFFFF',
    pillBg: 'linear-gradient(135deg, rgba(29,78,216,0.9), rgba(190,24,93,0.9))',
    pillBorder: '3px solid #FFFFFF',
    pillText: '#FFFFFF',
    progressGradient: 'linear-gradient(90deg, #FF4D6D 0%, #FFE500 55%, #38BDF8 100%)',
    ctaBg: 'linear-gradient(90deg, #E11D48, #2563EB)',
    ctaBorder: '2px solid #FFFFFF',
  },
};

export function resolveVisualTheme(themeId?: string): VisualThemeTokens {
  if (themeId && themeId !== 'auto' && themeId in VISUAL_THEMES) {
    return VISUAL_THEMES[themeId as Exclude<VisualThemeId, 'auto'>];
  }
  return VISUAL_THEMES.floral_rose;
}
