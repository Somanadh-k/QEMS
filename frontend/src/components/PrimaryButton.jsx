import React from 'react';
import SpecularButton from './SpecularButton/SpecularButton';
import './PrimaryButton.css';

/**
 * QEMS's primary-action button: SpecularButton (React Bits) themed to match the app's
 * muted, silk-toned palette and the Silk background, so CTAs read well against it
 * instead of the old flat gradient fill.
 */
export const PrimaryButton = ({ children, fullWidth = false, size = 'md', className = '', ...rest }) => (
  <SpecularButton
    size={size}
    radius={10}
    tint="#7B7481"
    tintOpacity={0.9}
    blur={0}
    textColor="#ffffff"
    lineColor="#ffffff"
    baseColor="#2e2a32"
    intensity={1.2}
    shineSize={16}
    shineFade={50}
    thickness={1.5}
    speed={0.4}
    followMouse
    proximity={220}
    autoAnimate={false}
    className={`qems-primary-btn${fullWidth ? ' qems-primary-btn--full' : ''}${className ? ` ${className}` : ''}`}
    {...rest}
  >
    {children}
  </SpecularButton>
);
