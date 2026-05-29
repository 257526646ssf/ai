import React, { useEffect, useRef } from 'react';

export default function InteractiveBackground() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    let animationFrameId;
    let particles = [];
    const particleCount = 55; // 略微增加数量以形成更密的神经网络
    const mouse = { x: null, y: null, radius: 150 };

    // 获取自适应的主题色
    const getAccentColor = () => {
      if (typeof window === 'undefined') return '#4f46e5';
      try {
        const themeElement = document.querySelector('[data-theme]');
        if (!themeElement) return '#4f46e5';
        
        const rootStyle = getComputedStyle(themeElement);
        const color = rootStyle.getPropertyValue('--accent-color').trim();
        
        if (!color || color.startsWith('var')) {
          return '#4f46e5';
        }
        return color;
      } catch (e) {
        return '#4f46e5';
      }
    };

    const resizeCanvas = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };

    window.addEventListener('resize', resizeCanvas);
    resizeCanvas();

    // 粒子结构
    class Particle {
      constructor() {
        this.reset(true);
      }

      reset(init = false) {
        this.x = Math.random() * canvas.width;
        this.y = init ? Math.random() * canvas.height : canvas.height + 20;
        this.size = Math.random() * 1.8 + 1; // 1px ~ 2.8px
        this.vx = (Math.random() - 0.5) * 0.35; // 水平漂移
        this.vy = -(Math.random() * 0.35 + 0.15); // 缓缓向上飘移
        this.alpha = Math.random() * 0.35 + 0.1;
        this.baseAlpha = this.alpha;
        this.phase = Math.random() * Math.PI * 2;
        this.phaseSpeed = Math.random() * 0.015 + 0.005;
      }

      update() {
        // 鼠标重力引力场交互
        if (mouse.x !== null && mouse.y !== null) {
          const dx = mouse.x - this.x;
          const dy = mouse.y - this.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          
          if (dist < mouse.radius) {
            // 产生柔和的吸引力，向鼠标方向微微加速
            const force = (mouse.radius - dist) / mouse.radius;
            const angle = Math.atan2(dy, dx);
            this.vx += Math.cos(angle) * force * 0.025;
            this.vy += Math.sin(angle) * force * 0.025;
          }
        }

        // 速度上限限速，保持优雅漂浮
        const speed = Math.sqrt(this.vx * this.vx + this.vy * this.vy);
        if (speed > 0.8) {
          this.vx = (this.vx / speed) * 0.8;
          this.vy = (this.vy / speed) * 0.8;
        }

        this.x += this.vx;
        this.y += this.vy;

        // 呼吸闪烁
        this.phase += this.phaseSpeed;
        this.alpha = this.baseAlpha + Math.sin(this.phase) * 0.06;
        if (this.alpha < 0.02) this.alpha = 0.02;
        if (this.alpha > 0.5) this.alpha = 0.5;

        // 越界重置
        if (this.y < -10 || this.x < -10 || this.x > canvas.width + 10) {
          this.reset();
        }
      }

      draw(color) {
        try {
          ctx.save();
          ctx.globalAlpha = this.alpha;
          ctx.beginPath();
          
          // 微发光晕渲染
          const grad = ctx.createRadialGradient(this.x, this.y, 0, this.x, this.y, this.size * 1.8);
          grad.addColorStop(0, color);
          grad.addColorStop(0.3, color);
          grad.addColorStop(1, 'transparent');
          
          ctx.fillStyle = grad;
          ctx.arc(this.x, this.y, this.size * 1.8, 0, Math.PI * 2);
          ctx.fill();
          ctx.restore();
        } catch (e) {
          ctx.save();
          ctx.globalAlpha = this.alpha;
          ctx.beginPath();
          ctx.fillStyle = '#4f46e5';
          ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
          ctx.fill();
          ctx.restore();
        }
      }
    }

    // 初始化粒子
    for (let i = 0; i < particleCount; i++) {
      particles.push(new Particle());
    }

    // 绘制神经网络连线
    const drawConnections = (color) => {
      for (let i = 0; i < particles.length; i++) {
        const p1 = particles[i];
        
        // 鼠标和粒子之间画一条极细的交互引力线
        if (mouse.x !== null && mouse.y !== null) {
          const mdx = mouse.x - p1.x;
          const mdy = mouse.y - p1.y;
          const mDist = Math.sqrt(mdx * mdx + mdy * mdy);
          
          if (mDist < 120) {
            ctx.save();
            ctx.beginPath();
            ctx.moveTo(p1.x, p1.y);
            ctx.lineTo(mouse.x, mouse.y);
            ctx.strokeStyle = color;
            ctx.lineWidth = 0.45;
            // 越近越亮，带有极高的透气度
            ctx.globalAlpha = ((120 - mDist) / 120) * 0.12; 
            ctx.stroke();
            ctx.restore();
          }
        }

        for (let j = i + 1; j < particles.length; j++) {
          const p2 = particles[j];
          const dx = p1.x - p2.x;
          const dy = p1.y - p2.y;
          const dist = Math.sqrt(dx * dx + dy * dy);

          // 当两个粒子靠近时，连线
          if (dist < 90) {
            ctx.save();
            ctx.beginPath();
            ctx.moveTo(p1.x, p1.y);
            ctx.lineTo(p2.x, p2.y);
            ctx.strokeStyle = color;
            ctx.lineWidth = 0.35;
            ctx.globalAlpha = ((90 - dist) / 90) * 0.08; // 非常淡的背景网，不遮挡内容
            ctx.stroke();
            ctx.restore();
          }
        }
      }
    };

    // 动画循环
    const animate = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const color = getAccentColor();

      // 先画线条网，使其被粒子盖在上方，显得有前后层次
      drawConnections(color);

      particles.forEach((p) => {
        p.update();
        p.draw(color);
      });

      animationFrameId = requestAnimationFrame(animate);
    };

    animate();

    // 鼠标监听
    const handleMouseMove = (e) => {
      mouse.x = e.clientX;
      mouse.y = e.clientY;
    };

    const handleMouseLeave = () => {
      mouse.x = null;
      mouse.y = null;
    };

    window.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseleave', handleMouseLeave);

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener('resize', resizeCanvas);
      window.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseleave', handleMouseLeave);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 pointer-events-none z-0 select-none"
      style={{ mixBlendMode: 'screen' }}
    />
  );
}

