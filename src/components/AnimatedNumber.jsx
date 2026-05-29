import React, { useState, useEffect } from 'react';

/**
 * AnimatedNumber - 物理弹性与动态运动模糊数字滚动组件
 * @param {Object} props
 * @param {string|number} props.value 目标数值（如: 1248, "1,248", "87.6%")
 * @param {number} props.duration 动画持续时间（毫秒），默认 1200ms
 * @param {number} props.delay 动画延迟时间（毫秒），默认 0ms
 */
export default function AnimatedNumber({ value, duration = 1200, delay = 0 }) {
  const [displayValue, setDisplayValue] = useState('0');
  const [blurPx, setBlurPx] = useState(0);

  useEffect(() => {
    // 解析输入值
    const parseValue = (val) => {
      try {
        if (val === undefined || val === null) {
          return { num: 0, format: 'number', prefix: '', suffix: '', decimalPlaces: 0 };
        }
        if (typeof val === 'number') {
          return { num: val, format: 'number', prefix: '', suffix: '', decimalPlaces: 0 };
        }
        
        const valStr = val.toString().trim();
        let prefix = '';
        let suffix = '';
        let cleanStr = valStr;

        // 提取前缀（如 ↑ 或 ↓）
        if (valStr.startsWith('↑') || valStr.startsWith('↓')) {
          prefix = valStr.substring(0, 1) + ' ';
          cleanStr = valStr.substring(1).trim();
        }

        // 提取后缀（如 %）
        if (cleanStr.endsWith('%')) {
          suffix = '%';
          cleanStr = cleanStr.slice(0, -1);
        }

        // 去除千分位逗号
        cleanStr = cleanStr.replace(/,/g, '');

        const parsedNum = parseFloat(cleanStr);
        const isDecimal = cleanStr.includes('.');
        const parts = cleanStr.split('.');
        const decimalPlaces = (isDecimal && parts[1]) ? parts[1].length : 0;

        const format = valStr.includes(',') ? 'comma' : (isDecimal ? 'decimal' : 'number');

        return {
          num: isNaN(parsedNum) ? 0 : parsedNum,
          format,
          prefix,
          suffix,
          decimalPlaces
        };
      } catch (err) {
        return { num: 0, format: 'number', prefix: '', suffix: '', decimalPlaces: 0 };
      }
    };

    const info = parseValue(value);
    let startTimestamp = null;
    let timerId = null;
    let lastNum = 0;

    const startAnimation = () => {
      const step = (timestamp) => {
        try {
          if (!startTimestamp) startTimestamp = timestamp;
          const progress = Math.min((timestamp - startTimestamp) / duration, 1);
          
          // 物理弹性曲线 (Back-Overshoot)
          // 冲出终点后微弱反弹归位: t = progress
          const easeOutBack = (t) => {
            const c1 = 0.55; // 限制回弹幅度，使其自然细微
            const c3 = c1 + 1;
            return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
          };

          const springProgress = easeOutBack(progress);
          const currentNum = springProgress * info.num;

          // 计算速度差来确定运动模糊像素 (Motion Blur)
          const velocity = Math.abs(currentNum - lastNum);
          lastNum = currentNum;
          
          // 速度越大，模糊半径越大，最高限制在 1.5px (不影响整体轮廓)
          const currentBlur = Math.min(velocity * 0.08, 1.6);
          
          // 接近终点时让模糊迅速归零，保证最终文字绝对清晰
          if (progress > 0.92) {
            setBlurPx(0);
          } else {
            setBlurPx(currentBlur);
          }

          // 格式化当前数值
          let formattedNum = '';
          if (info.format === 'comma') {
            formattedNum = Math.round(currentNum).toLocaleString('zh-CN');
          } else if (info.format === 'decimal') {
            formattedNum = currentNum.toFixed(info.decimalPlaces || 0);
          } else {
            formattedNum = Math.round(currentNum).toString();
          }

          setDisplayValue(`${info.prefix}${formattedNum}${info.suffix}`);

          if (progress < 1) {
            timerId = requestAnimationFrame(step);
          } else {
            setBlurPx(0); // 结束强制复原
          }
        } catch (err) {
          setDisplayValue(value ? value.toString() : '0');
          setBlurPx(0);
        }
      };
      timerId = requestAnimationFrame(step);
    };

    // 延迟执行
    let delayTimer = null;
    if (delay > 0) {
      delayTimer = setTimeout(startAnimation, delay);
    } else {
      startAnimation();
    }

    return () => {
      if (timerId) cancelAnimationFrame(timerId);
      if (delayTimer) clearTimeout(delayTimer);
    };
  }, [value, duration, delay]);

  return (
    <span 
      className="quantum-digit-lock"
      style={{ 
        filter: blurPx > 0.15 ? `blur(${blurPx.toFixed(2)}px)` : 'none',
        display: 'inline-block',
        transition: 'filter 0.05s ease-out'
      }}
    >
      {displayValue}
    </span>
  );
}
