'use client';

import React from 'react';
import { useTheme } from 'next-themes';
import { Monitor, Moon, Palette, Sun, X } from 'lucide-react';
import { buttonVariants, dialogVariants } from '@/lib/styles/button-variants';

const CUSTOM_COLORS_KEY = 'isocrates-custom-colors';

interface CustomColors {
  background: string;
  foreground: string;
}

const DEFAULT_CUSTOM_COLORS: CustomColors = {
  background: '#f5f7f8',
  foreground: '#152041',
};

function loadCustomColors(): CustomColors {
  if (typeof window === 'undefined') return DEFAULT_CUSTOM_COLORS;
  try {
    const stored = localStorage.getItem(CUSTOM_COLORS_KEY);
    if (stored) return JSON.parse(stored);
  } catch {}
  return DEFAULT_CUSTOM_COLORS;
}

function saveCustomColors(colors: CustomColors) {
  localStorage.setItem(CUSTOM_COLORS_KEY, JSON.stringify(colors));
}

function hexToHsl(hex: string): string {
  const r = parseInt(hex.slice(1, 3), 16) / 255;
  const g = parseInt(hex.slice(3, 5), 16) / 255;
  const b = parseInt(hex.slice(5, 7), 16) / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  let h = 0, s = 0;
  const l = (max + min) / 2;
  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r: h = ((g - b) / d + (g < b ? 6 : 0)) / 6; break;
      case g: h = ((b - r) / d + 2) / 6; break;
      case b: h = ((r - g) / d + 4) / 6; break;
    }
  }
  return `${Math.round(h * 360)} ${Math.round(s * 100)}% ${Math.round(l * 100)}%`;
}

function applyCustomColors(colors: CustomColors) {
  const root = document.documentElement;
  root.style.setProperty('--background', hexToHsl(colors.background));
  root.style.setProperty('--foreground', hexToHsl(colors.foreground));
}

function clearCustomColors() {
  const root = document.documentElement;
  root.style.removeProperty('--background');
  root.style.removeProperty('--foreground');
}

interface SettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SettingsDialog({ open, onOpenChange }: SettingsDialogProps) {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = React.useState(false);
  const [customColors, setCustomColors] = React.useState<CustomColors>(DEFAULT_CUSTOM_COLORS);

  React.useEffect(() => {
    setMounted(true);
    const colors = loadCustomColors();
    setCustomColors(colors);
    // Apply custom colors on mount if custom theme is active
    if (document.documentElement.classList.contains('custom')) {
      applyCustomColors(colors);
    }
  }, []);

  // When theme changes, apply or clear custom CSS variables
  React.useEffect(() => {
    if (!mounted) return;
    if (theme === 'custom') {
      applyCustomColors(customColors);
    } else {
      clearCustomColors();
    }
  }, [theme, mounted]);

  const handleCustomColorChange = (key: keyof CustomColors, value: string) => {
    const updated = { ...customColors, [key]: value };
    setCustomColors(updated);
    saveCustomColors(updated);
    if (theme === 'custom') {
      applyCustomColors(updated);
    }
  };

  const handleSetTheme = (newTheme: string) => {
    if (newTheme !== 'custom') {
      clearCustomColors();
    }
    setTheme(newTheme);
    if (newTheme === 'custom') {
      applyCustomColors(customColors);
    }
  };

  if (!open) return null;

  const themeButtonClass = (value: string) =>
    `flex flex-col items-center gap-3 rounded-lg border-2 p-5 transition-all ${
      theme === value
        ? 'border-primary bg-accent'
        : 'border-border hover:bg-accent/50'
    }`;

  return (
    <div className={dialogVariants.overlay} onClick={() => onOpenChange(false)}>
      <div
        className={`${dialogVariants.container} max-w-lg`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className={dialogVariants.content}>
          {/* Header */}
          <div className={dialogVariants.header}>
            <h2 className={dialogVariants.title}>Settings</h2>
            <button
              onClick={() => onOpenChange(false)}
              className={buttonVariants.icon}
              aria-label="Close"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Content */}
          <div className={`${dialogVariants.body} space-y-6`}>
            {/* Appearance Section */}
            <div>
              <h3 className="text-lg font-medium mb-4">Appearance</h3>
              <div className="space-y-3">
                <p className="text-sm text-muted-foreground mb-4">
                  Choose your preferred theme
                </p>

                {mounted && (
                  <>
                    <div className="grid grid-cols-4 gap-3">
                      <button onClick={() => handleSetTheme('light')} className={themeButtonClass('light')}>
                        <Sun className="h-6 w-6" />
                        <span className="text-sm font-medium">Light</span>
                      </button>

                      <button onClick={() => handleSetTheme('dark')} className={themeButtonClass('dark')}>
                        <Moon className="h-6 w-6" />
                        <span className="text-sm font-medium">Dark</span>
                      </button>

                      <button onClick={() => handleSetTheme('system')} className={themeButtonClass('system')}>
                        <Monitor className="h-6 w-6" />
                        <span className="text-sm font-medium">System</span>
                      </button>

                      <button onClick={() => handleSetTheme('custom')} className={themeButtonClass('custom')}>
                        <Palette className="h-6 w-6" />
                        <span className="text-sm font-medium">Custom</span>
                      </button>
                    </div>

                    {theme === 'custom' && (
                      <div className="mt-4 space-y-3 rounded-lg border border-border p-4">
                        <p className="text-sm font-medium mb-3">Custom Colors</p>
                        <div className="flex items-center justify-between">
                          <label className="text-sm text-muted-foreground">Background</label>
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-muted-foreground font-mono">{customColors.background}</span>
                            <input
                              type="color"
                              value={customColors.background}
                              onChange={(e) => handleCustomColorChange('background', e.target.value)}
                              className="h-8 w-8 cursor-pointer rounded border border-border bg-transparent"
                            />
                          </div>
                        </div>
                        <div className="flex items-center justify-between">
                          <label className="text-sm text-muted-foreground">Text</label>
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-muted-foreground font-mono">{customColors.foreground}</span>
                            <input
                              type="color"
                              value={customColors.foreground}
                              onChange={(e) => handleCustomColorChange('foreground', e.target.value)}
                              className="h-8 w-8 cursor-pointer rounded border border-border bg-transparent"
                            />
                          </div>
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>

            {/* About Section */}
            <div>
              <h3 className="text-lg font-medium mb-4">About</h3>
              <div className="text-sm text-muted-foreground space-y-2">
                <p>IsoCrates v1.0.0</p>
                <p>AI-powered technical documentation platform</p>
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className={`${dialogVariants.footer} justify-center`}>
            <button onClick={() => onOpenChange(false)} className={buttonVariants.primary}>
              Done
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
