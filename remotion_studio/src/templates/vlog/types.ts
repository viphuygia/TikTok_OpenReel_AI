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

export type VlogStickerProps = {
  emoji: string;
  label: string;
  sublabel?: string;
  position?: 'top-right' | 'top-left' | 'bottom-right';
  accentColor?: string;
  durationSec?: number;
  width?: number;
  height?: number;
  aspectRatio?: '16:9' | '9:16';
};
