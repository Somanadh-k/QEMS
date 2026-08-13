import React from 'react';

const initialsFrom = (name = '') =>
  name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() || '')
    .join('') || '?';

/**
 * Shows the user's picture if one is set; otherwise a plain initials circle instead of a
 * broken <img> or a fake stock photo.
 */
export const Avatar = ({ src, name, size = 40, style: styleOverride }) => {
  const style = {
    width: size,
    height: size,
    borderRadius: '50%',
    objectFit: 'cover',
    flexShrink: 0,
    ...styleOverride,
  };

  if (src) {
    return <img src={src} alt={name} style={style} />;
  }

  return (
    <div
      style={{
        ...style,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--primary-light)',
        color: 'var(--primary)',
        fontWeight: 700,
        fontSize: size * 0.4,
      }}
      aria-label={name}
      title={name}
    >
      {initialsFrom(name)}
    </div>
  );
};
