import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgVolumeHalf = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M15.537 15.978C16.699 15.256 17.5 13.754 17.5 12.005C17.5 10.256 16.699 8.75297 15.537 8.02197M5.875 8.62498H3.5C2.948 8.62498 2.5 9.07298 2.5 9.62498V14.375C2.5 14.927 2.948 15.375 3.5 15.375H5.875L9.854 18.746C10.504 19.297 11.5 18.835 11.5 17.983V6.01698C11.5 5.16498 10.503 4.70298 9.854 5.25398L5.875 8.62498Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgVolumeHalf);
export default Memo;