export type VlogTitleStyle =
  | 'cinematic_glass'
  | 'editorial_minimal'
  | 'campfire_warm'
  | 'adventure_bold'
  | 'pastel_soft';

export type VlogIntroProps = {
  title: string;
  subtitle: string;
  badgeText?: string;
  accentColor?: string;
  titleStyle?: VlogTitleStyle;
  durationSec?: number;
  width?: number;
  height?: number;
  aspectRatio?: '16:9' | '9:16';
};

export type VlogChapterProps = {
  chapterNumber: string;
  title: string;
  subtitle?: string;
  accentColor?: string;
  titleStyle?: VlogTitleStyle;
  durationSec?: number;
  width?: number;
  height?: number;
  aspectRatio?: '16:9' | '9:16';
};

export type VlogOutroProps = {
  title: string;
  subtitle: string;
  ctaText: string;
  channelName?: string;
  accentColor?: string;
  titleStyle?: VlogTitleStyle;
  durationSec?: number;
  width?: number;
  height?: number;
  aspectRatio?: '16:9' | '9:16';
};

export type VlogStickerVariant = 'pill' | 'callout' | 'lower_third' | 'floating_lottie' | 'pointer';

export type VlogStickerProps = {
  emoji: string;
  label: string;
  sublabel?: string;
  position?: 'top-right' | 'top-left' | 'bottom-right' | 'bottom-left' | 'center-left' | 'center-right';
  variant?: VlogStickerVariant;
  targetX?: number;
  targetY?: number;
  accentColor?: string;
  durationSec?: number;
  width?: number;
  height?: number;
  aspectRatio?: '16:9' | '9:16';
};
