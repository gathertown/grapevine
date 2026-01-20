export interface CircleConfig {
  cx: number;
  cy: number;
  diameter: number;
  /**
   * @default '100%'
   */
  borderRadius?: number | '100%';
}
export const generateClipPathWithMultiCircleCutout = (circles: CircleConfig[]) => {
  const square = `M 0,0 H 100 V 100 H 0 Z`;

  const circleCutout = circles.map(({ cx, cy, diameter, borderRadius }) => {
    if (typeof borderRadius === 'number') {
      // Draw a rounded rectangle cutout instead of a circle

      const size = diameter;
      // keep same behavior as circle that cx and cy are the center of the circle / rounded rectangle
      const topStart = cy - size / 2;
      const leftStart = cx - size / 2;
      const corners = {
        topLeft: {
          x: leftStart,
          y: topStart,
        },
        topRight: {
          x: leftStart + size,
          y: topStart,
        },
        bottomRight: {
          x: leftStart + size,
          y: topStart + size,
        },
        bottomLeft: {
          x: leftStart,
          y: topStart + size,
        },
      };
      /**
       * note: we have to draw counter-clockwise in order for the shape to be subtracted
       * from the square.
       */
      const topLine = `M${corners.topRight.x - borderRadius} ${corners.topRight.y} L${
        corners.topLeft.x + borderRadius
      } ${corners.topLeft.y}`;
      const topLeftCorner = `Q ${corners.topLeft.x} ${corners.topLeft.y}, ${corners.topLeft.x} ${
        corners.topLeft.y + borderRadius
      }`;
      const leftLine = `L ${corners.bottomLeft.x} ${corners.bottomLeft.y - borderRadius}`;
      const bottomLeftCorner = `Q ${corners.bottomLeft.x} ${corners.bottomLeft.y}, ${
        corners.bottomLeft.x + borderRadius
      } ${corners.bottomLeft.y}`;
      const bottomLine = `L ${corners.bottomRight.x - borderRadius} ${corners.bottomRight.y}`;
      const bottomRightCorner = `Q ${corners.bottomRight.x} ${corners.bottomRight.y}, ${
        corners.bottomRight.x
      } ${corners.bottomRight.y - borderRadius}`;
      const rightLine = `L ${corners.topRight.x} ${corners.topRight.y + borderRadius}`;
      const topRightCorner = `Q ${corners.topRight.x} ${corners.topRight.y}, ${
        corners.topRight.x - borderRadius
      } ${corners.topRight.y}`;

      return [
        topLine,
        topLeftCorner,
        leftLine,
        bottomLeftCorner,
        bottomLine,
        bottomRightCorner,
        rightLine,
        topRightCorner,
      ].join(' ');
    } else {
      // Default: circle cutout
      const radius = diameter / 2;
      const arc = radius;
      const leftHalfCircle = `a ${arc},${arc} 0 1,0 ${-diameter},0`;
      const rightHalfCircle = `a ${arc},${arc} 0 1,0 ${diameter},0`;
      return `M ${cx} ${cy} m ${radius},0 ${leftHalfCircle} ${rightHalfCircle} `;
    }
  });

  return `path('${square} ${circleCutout}')`;
};

export const generateInvertedCircleClipPath = (cx: number, cy: number, diameter: number) =>
  generateClipPathWithMultiCircleCutout([{ cx, cy, diameter }]);
