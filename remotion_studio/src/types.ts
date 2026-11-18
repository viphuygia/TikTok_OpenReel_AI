export type ColorToken = {
  text: string;
  color: string;
  strokeColor?: string;
};

export type CalloutLine = {
  tokens: ColorToken[];
};

export type CalloutItem = {
  id: string;
  start: number;
  end: number;
  y?: number;
  lines: CalloutLine[];
  fontSize?: number;
};

export type FloralBadgeConfig = {
  enabled: boolean;
  brand: string;
  productLine: string;
  category: string;
  brandColor?: string;
  productColor?: string;
  categoryColor?: string;
  accentStrokeColor?: string;
  outerStrokeColor?: string;
  start?: number;
  end?: number;
  y?: number;
};

export type WordTimestamp = {
  word: string;
  start: number;
  end: number;
};

export type VideoClipItem = {
  id: string;
  src: string; // relative path inside public/, e.g. "workspace/01_clips/clip_01.mp4"
  startInTimeline: number;
  duration: number;
  zoomMode?: 'push_in' | 'zoom_out' | 'punch_in' | 'in_out' | 'ken_burns';
  zoomFrom?: number;
  zoomTo?: number;
  panX?: number;
  panY?: number;
  transitionType?: 'hard' | 'flash' | 'zoom' | 'slide';
  beatIndex?: number;
  spokenText?: string;
  calloutText?: string;
  featurePill?: string;
  note?: string;
};

export type SfxEvent = {
  id: string;
  src: string; // relative path inside public/, e.g. "workspace/audio/sfx_pop.wav"
  start: number;
  duration: number;
  volume?: number;
};

export type WildcardLayoutArchetype =
  | 'polaroid_scrapbook'
  | 'bento_split'
  | 'kinetic_poster'
  | 'tech_hud'
  | 'editorial_zine'
  | 'cinema_spotlight';

export type WildcardMotifKind =
  | 'bubbles_ice'
  | 'botanical_leaf'
  | 'cyber_grid'
  | 'sparkle_burst'
  | 'wave_ribbon'
  | 'geometric_orbit';

export type WildcardStickerEvent = {
  emoji: string;
  label: string;
  stickerAsset?: string;
  styleKind?: 'animated_sticker' | 'messenger_bubble';
  start: number;
  duration: number;
  xPct: number;
  yPct: number;
  bg: string;
  rotateDeg?: number;
};

export type WildcardStyleSpec = {
  styleName: string;
  layoutArchetype?: WildcardLayoutArchetype;
  motifKind?: WildcardMotifKind;
  tickerText?: string;
  customSvgOverlay?: string;
  popPalette?: string[];
  stickerEvents?: WildcardStickerEvent[];
  frameScale: number;
  frameRadius: number;
  frameTiltDeg: number;
  frameBorderColor: string;
  letterboxPx: number;
  bgGradient: string;
  accentColor: string;
  textColor: string;
  hookLayout: 'top_left_editorial' | 'center_bold' | 'quote_5star' | 'breaking_ticker' | 'glass_floating';
  subtitleVariant: 'clean_stroke' | 'glass_pill' | 'accent_band';
  subtitleY: number;
  showRatingBadge: boolean;
  ctaLabel: string;
};

export type TikTokVideoProps = {
  title?: string;
  durationSec: number;
  badgeStyle: 'floral_plus_callouts' | 'multicolor_pill' | 'floral_badge';
  visualTheme?: 'auto' | 'floral_rose' | 'fresh_mint' | 'flash_gold' | 'luxury_dark' | 'ribbon_sticker';
  layoutStyle?: 'full' | 'card_blur' | 'top_banner';
  colorPreset?: 'natural' | 'warm_film' | 'cool_vivid';
  creativeMode?: 'classic_dna' | 'breakthrough_ai' | 'flash_checklist';
  cameraIntensity?: 'subtle' | 'dynamic_ai' | 'energetic';
  selectedScriptId?: string;
  selectedScriptLabel?: string;
  outputFilename?: string;
  transparentBg?: boolean;
  badgeOnly?: boolean;
  hookY: number;
  subtitleY: number;
  fontHeading?: string;
  fontBrand?: string;
  fontScript?: string;
  subtitleActiveColor: string;
  floralBadge: FloralBadgeConfig;
  callouts: CalloutItem[];
  words: WordTimestamp[];
  clips: VideoClipItem[];
  voiceSrc?: string;
  bgmSrc?: string;
  bgmVolume?: number;
  sfxEvents?: SfxEvent[];
  sfxVolume?: number;
  renderEngine?: 'remotion_classic' | 'remotion_innovation' | 'hyperframes';
  innovationPreset?: 'kinetic_pop' | 'magazine_split' | 'neon_pulse';
  transitionLevel?: 'gentle' | 'balanced' | 'energetic';
  disableFlashShake?: boolean;
  iconDensity?: 'minimal' | 'balanced' | 'expressive';
  stickerDensity?: 'off' | 'normal' | 'rich';
  overlayEffect?: string;
  wildcardSpec?: WildcardStyleSpec;
};
