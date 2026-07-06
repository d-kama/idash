import { describe, expect, it } from 'vitest';
import { formatPercent, formatSigned, formatYen } from './format';

describe('formatYen', () => {
  it('円整数を ¥ + 桁区切りで整形する', () => {
    expect(formatYen(2_480_000)).toBe('¥2,480,000');
  });

  it('0 は ¥0', () => {
    expect(formatYen(0)).toBe('¥0');
  });

  it('負値は先頭に - を付ける（会計表記でなく符号）', () => {
    expect(formatYen(-80_000)).toBe('-¥80,000');
  });
});

describe('formatSigned', () => {
  it('正値は明示的な + を付ける（損益表示向け）', () => {
    expect(formatSigned(180_000)).toBe('+¥180,000');
  });

  it('0 は符号なし ¥0', () => {
    expect(formatSigned(0)).toBe('¥0');
  });

  it('負値は - 付き', () => {
    expect(formatSigned(-8_000)).toBe('-¥8,000');
  });
});

describe('formatPercent', () => {
  it('生比率を符号付き2桁%へ（domain の +.2f 相当）', () => {
    expect(formatPercent(0.0783)).toBe('+7.83%');
  });

  it('負の比率', () => {
    expect(formatPercent(-0.0321)).toBe('-3.21%');
  });

  it('0 も符号付き（+0.00%）', () => {
    expect(formatPercent(0)).toBe('+0.00%');
  });
});
