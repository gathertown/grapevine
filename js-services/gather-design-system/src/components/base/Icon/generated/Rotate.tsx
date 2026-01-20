import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgRotate = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M19.704 7.748H19.931H17.669H20.32V5.096M4.15 7.748C5.395 4.672 8.401 2.5 11.924 2.5C15.447 2.5 18.458 4.672 19.705 7.748M5.929 16.216L10.655 20.942C11.399 21.686 12.606 21.686 13.35 20.942L18.076 16.216C18.82 15.472 18.82 14.265 18.076 13.521L13.35 8.795C12.606 8.051 11.399 8.051 10.655 8.795L5.929 13.521C5.185 14.265 5.185 15.472 5.929 16.216Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgRotate);
export default Memo;