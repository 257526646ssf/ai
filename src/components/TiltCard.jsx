import React, { useState } from 'react';

/**
 * TiltCard - 裸眼 3D 视差深度与反射眩光卡片组件
 * @param {Object} props
 * @param {React.ReactNode} props.children 子组件
 * @param {string} props.className 自定义类名
 * @param {number} props.maxRotation 最大旋转角度，默认为 5 度
 * @param {number} props.scale 悬停时缩放比例，默认为 1.02
 */
export default function TiltCard({ 
  children, 
  className = '', 
  maxRotation = 5, 
  scale = 1.02 
}) {
  const [tiltStyle, setTiltStyle] = useState({
    transform: 'perspective(1000px) rotateX(0deg) rotateY(0deg) scale3d(1, 1, 1)',
    transition: 'all 0.6s cubic-bezier(0.16, 1, 0.3, 1)',
    transformStyle: 'preserve-3d'
  });

  const [glareStyle, setGlareStyle] = useState({
    '--mouse-x': '50%',
    '--mouse-y': '50%',
    opacity: 0,
    transform: 'translateZ(8px)' // 眩光层稍微悬浮在卡片底座上
  });

  const handleMouseMove = (e) => {
    if (e.target.closest('button, input, textarea, select, a, [role="button"]')) {
      return;
    }

    const card = e.currentTarget;
    const rect = card.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    // 归一化坐标在 -1 到 1 之间
    const px = (x / rect.width - 0.5) * 2;
    const py = (y / rect.height - 0.5) * 2;

    const rotateX = -py * maxRotation;
    const rotateY = px * maxRotation;

    setTiltStyle({
      transform: `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) scale3d(${scale}, ${scale}, ${scale})`,
      transition: 'transform 0.1s cubic-bezier(0.25, 1, 0.5, 1), box-shadow 0.15s cubic-bezier(0.25, 1, 0.5, 1)',
      boxShadow: '0 20px 40px var(--accent-glow)',
      transformStyle: 'preserve-3d'
    });

    setGlareStyle({
      '--mouse-x': `${x}px`,
      '--mouse-y': `${y}px`,
      opacity: 1,
      transform: 'translateZ(10px)'
    });
  };

  const handleMouseLeave = () => {
    setTiltStyle({
      transform: 'perspective(1000px) rotateX(0deg) rotateY(0deg) scale3d(1, 1, 1)',
      transition: 'all 0.6s cubic-bezier(0.16, 1, 0.3, 1)',
      boxShadow: 'none',
      transformStyle: 'preserve-3d'
    });

    setGlareStyle({
      '--mouse-x': '50%',
      '--mouse-y': '50%',
      opacity: 0,
      transform: 'translateZ(8px)'
    });
  };

  return (
    <div
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      style={tiltStyle}
      className={`theme-card relative group ${className}`}
    >
      {/* 眩光物理高光层 (translateZ(10px)) */}
      <div 
        className="glass-glare" 
        style={glareStyle} 
      />
      {/* 内容插槽容器 - 继承 preserve-3d，使子节点能够通过 translateZ 产生视差层 */}
      <div 
        className="relative z-10 w-full h-full"
        style={{ transformStyle: 'preserve-3d' }}
      >
        {children}
      </div>
    </div>
  );
}
