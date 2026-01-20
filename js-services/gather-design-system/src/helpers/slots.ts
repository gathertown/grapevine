/* eslint-disable @typescript-eslint/consistent-type-assertions */
import React, { ComponentType } from 'react';

export const assignSlots = <
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  BaseComponent extends ComponentType<any>,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  Slots extends Record<string, ComponentType<any>>,
>(
  Component: BaseComponent,
  slots: {
    [K in keyof Slots]: Exclude<Slots[K], null | undefined>;
  }
) => Object.assign(Component, slots);

export const extractSlotComponentsFromChildren = <T extends Record<string, React.ElementType>>(
  children: React.ReactNode,
  slots: T
): { [K in keyof T]?: React.FC<React.ComponentProps<T[K]>> | undefined } & {
  passThrough: React.ReactNode[];
} => {
  const slotExtractionResult = {
    passThrough: [] as React.ReactNode[],
  } as { [K in keyof T]?: React.FC<React.ComponentProps<T[K]>> } & {
    passThrough: React.ReactNode[];
  };

  React.Children.forEach(children, (child) => {
    if (React.isValidElement(child)) {
      const matchedSlot = Object.entries(slots).find(([, childSlot]) => child.type === childSlot);

      if (matchedSlot) {
        const [childSlotName] = matchedSlot as [
          keyof T,
          React.FC<React.ComponentProps<T[keyof T]>>,
        ];
        const slotElement: React.FC<React.ComponentProps<T[typeof childSlotName]>> = (props) =>
          React.cloneElement(child, props);

        slotElement.displayName =
          (child.type as React.ComponentType).displayName ||
          (child.type as React.ComponentType).name;
        Object.assign(slotExtractionResult, {
          [childSlotName]: slotElement,
        });
      } else {
        slotExtractionResult.passThrough = [...slotExtractionResult.passThrough, child];
      }
    } else {
      slotExtractionResult.passThrough = [...slotExtractionResult.passThrough, child];
    }
  });

  return slotExtractionResult;
};
