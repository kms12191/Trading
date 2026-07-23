'use client';
import { useRef, useState, useCallback, useEffect } from 'react';

import { motion, useSpring, useTransform } from 'framer-motion';
import { cn } from '@/lib/utils';

export function Spotlight({
  className,
  size = 200,
  springOptions = { bounce: 0 },
}) {
  const containerRef = useRef(null);
  const [isHovered, setIsHovered] = useState(false);
  const [parentElement, setParentElement] = useState(null);

  const mouseX = useSpring(0, springOptions);
  const mouseY = useSpring(0, springOptions);

  const spotlightLeft = useTransform(mouseX, (x) => `${x - size / 2}px`);
  const spotlightTop = useTransform(mouseY, (y) => `${y - size / 2}px`);

  // 부모 엘리먼트를 찾아서 상대 스타일 지정
  useEffect(() => {
    if (containerRef.current) {
      const parent = containerRef.current.parentElement;
      if (parent) {
        parent.style.position = 'relative';
        parent.style.overflow = 'hidden';
        setParentElement(parent);
      }
    }
  }, []);

  const handleMouseMove = useCallback(
    (event) => {
      if (!parentElement) return;

      const { left, top, width, height } = parentElement.getBoundingClientRect();
      const x = event.clientX - left;
      const y = event.clientY - top;

      // 마우스가 부모 엘리먼트 영역 내에 있는지 수학적으로 검증 (Spline 이벤트 캡처 폴백)
      if (
        event.clientX >= left &&
        event.clientX <= left + width &&
        event.clientY >= top &&
        event.clientY <= top + height
      ) {
        setIsHovered(true);
        mouseX.set(x);
        mouseY.set(y);
      } else {
        setIsHovered(false);
      }
    },
    [mouseX, mouseY, parentElement]
  );

  useEffect(() => {
    if (!parentElement) return;

    // 3D Canvas의 이벤트 차단을 우회하기 위해 window 전역 객체에 mousemove 리스너를 등록합니다.
    window.addEventListener('mousemove', handleMouseMove);

    const handleMouseEnter = () => setIsHovered(true);
    const handleMouseLeave = () => setIsHovered(false);

    parentElement.addEventListener('mouseenter', handleMouseEnter);
    parentElement.addEventListener('mouseleave', handleMouseLeave);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      parentElement.removeEventListener('mouseenter', handleMouseEnter);
      parentElement.removeEventListener('mouseleave', handleMouseLeave);
    };
  }, [parentElement, handleMouseMove]);

  return (
    <motion.div
      ref={containerRef}
      className={cn(
        'pointer-events-none absolute rounded-full blur-xl transition-opacity duration-200',
        isHovered ? 'opacity-100' : 'opacity-0',
        className
      )}
      style={{
        width: size,
        height: size,
        left: spotlightLeft,
        top: spotlightTop,
        // Tailwind v4 그라디언트 파싱 오동작 방지를 위해 인라인 스타일로 화이트 광원 그라디언트를 직접 지정합니다.
        backgroundImage: 'radial-gradient(circle at center, rgba(255, 255, 255, 0.2) 0%, rgba(255, 255, 255, 0) 80%)',
      }}
    />
  );
}
