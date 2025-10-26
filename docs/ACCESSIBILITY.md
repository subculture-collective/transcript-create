# Accessibility & UX Features

This document describes the accessibility and user experience improvements implemented in the Transcript Search application.

## Accessibility Features (WCAG 2.1 AA Compliant)

### Keyboard Navigation

- **Skip to Content**: Press `Tab` on page load to reveal a "Skip to main content" link that allows keyboard users to bypass navigation
- **Search Shortcut**: Press `/` anywhere on the search page to focus the search input
- **Tab Order**: Logical tab order through all interactive elements
- **Focus Indicators**: Visible focus outlines (2px blue) on all focusable elements
- **Escape to Close**: Mobile menu closes with `Escape` key

### Semantic HTML

- Proper heading hierarchy (h1 → h2 → h3)
- ARIA labels on all interactive elements
- Semantic landmarks:
  - `<header role="banner">` for site header
  - `<main role="main">` for primary content
  - `<nav role="navigation">` for navigation menus
  - `<footer role="contentinfo">` for site footer
  - `<article>` for search results

### Screen Reader Support

- All images have descriptive `alt` text
- Loading states use `aria-live="polite"` for announcements
- Buttons have descriptive `aria-label` attributes
- Form inputs properly associated with labels
- Status messages use appropriate ARIA attributes

### Touch Targets

- All interactive elements meet minimum 44x44px touch target size
- Adequate spacing between clickable elements
- Touch-friendly mobile navigation

### Color Contrast

- Text contrast ratios meet WCAG AA standards (4.5:1 for normal text, 3:1 for large text)
- Dark mode also meets contrast requirements
- Focus indicators are clearly visible against all backgrounds

### Visual Accessibility

- Respects `prefers-reduced-motion` - disables animations when user prefers reduced motion
- System dark mode preference automatically detected
- Clear visual feedback for interactive states (hover, focus, active)

## Responsive Design

### Breakpoints

- **Mobile**: 320px - 768px
  - Hamburger menu for navigation
  - Single column layout
  - Stacked form inputs
  - Full-width cards

- **Tablet**: 768px - 1024px
  - Responsive grid layouts
  - Optimized spacing

- **Desktop**: 1024px+
  - Multi-column layouts
  - Full horizontal navigation
  - Wider containers (max-width: 1280px)

### Mobile Optimizations

- Touch-friendly button sizes (min 44x44px)
- Mobile-first CSS approach
- Hamburger menu with smooth transitions
- Responsive typography with fluid sizing
- Horizontal scroll prevention

## Progressive Web App (PWA)

### Installation

The app can be installed on mobile devices and desktop:
- **iOS**: Tap Share → Add to Home Screen
- **Android**: Tap Menu → Install app
- **Desktop**: Look for install prompt in address bar

### Offline Support

- Service worker caches essential assets
- Offline fallback page with helpful message
- Graceful degradation when offline
- Background sync when connection restored

### Features

- Standalone app experience
- Custom app icon
- Splash screen
- Theme color for mobile UI

## Dark Mode

### Activation

- **Manual Toggle**: Click sun/moon icon in header
- **System Preference**: Automatically follows OS dark mode setting
- **Persistence**: Choice saved in localStorage

### Implementation

- Comprehensive dark color palette
- Smooth transitions between themes
- Meta theme-color updates dynamically
- Proper contrast in both themes

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `/` | Focus search input |
| `Tab` | Navigate forward through interactive elements |
| `Shift + Tab` | Navigate backward through interactive elements |
| `Enter` | Submit forms / activate buttons |
| `Escape` | Close modals and mobile menu |
| `Space` | Activate buttons |

## Loading States

- Animated spinners for async operations
- Loading text with `aria-live` announcements
- Skeleton screens for content placeholders
- Disabled state for buttons during processing

## Empty States

- Helpful messages when no results found
- Suggestions for different search terms
- Clear iconography
- Encouraging call-to-action

## Form Improvements

- Real-time validation (where implemented)
- Clear button in search input
- Loading states on submit buttons
- Error messages with clear guidance
- Success feedback for actions

## Performance Considerations

- Minimal bundle size (gzipped CSS: ~5.6KB, JS: ~101KB)
- Code organized for potential route-based splitting
- Lazy loading prepared for heavy components
- Optimized fonts and assets
- Service worker caching for repeat visits

## Browser Support

- Modern evergreen browsers (Chrome, Firefox, Safari, Edge)
- iOS Safari 12+
- Chrome for Android
- Progressive enhancement for older browsers

## Testing Recommendations

### Manual Testing Checklist

- [ ] Tab through all pages and verify focus order
- [ ] Test with screen reader (NVDA on Windows, VoiceOver on macOS/iOS)
- [ ] Verify color contrast with browser DevTools
- [ ] Test on mobile devices (iOS and Android)
- [ ] Verify PWA installation works
- [ ] Test dark mode toggle and system preference
- [ ] Test keyboard shortcuts
- [ ] Verify responsive layouts at all breakpoints
- [ ] Test with browser zoom (100% - 200%)
- [ ] Verify reduced motion preference is respected

### Automated Testing

- Run axe-core accessibility checker in browser DevTools
- Use Lighthouse for comprehensive audit
- Test with WAVE browser extension
- Validate HTML at validator.w3.org

## Future Enhancements

Potential improvements for future iterations:

- [ ] Toast notifications for copy actions
- [ ] More keyboard shortcuts (arrow keys for navigation)
- [ ] Advanced search filters with accessible controls
- [ ] Internationalization (i18n) support
- [ ] High contrast mode
- [ ] Font size preferences
- [ ] Customizable keyboard shortcuts
- [ ] Voice search integration
- [ ] More comprehensive offline functionality

## Resources

- [WCAG 2.1 Guidelines](https://www.w3.org/WAI/WCAG21/quickref/)
- [MDN Accessibility](https://developer.mozilla.org/en-US/docs/Web/Accessibility)
- [WebAIM Resources](https://webaim.org/)
- [PWA Documentation](https://web.dev/progressive-web-apps/)
