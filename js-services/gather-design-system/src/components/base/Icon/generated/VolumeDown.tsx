import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgVolumeDown = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M21.33 11.94H15.33M5.875 8.62498L9.854 5.25398C10.504 4.70298 11.5 5.16498 11.5 6.01698V17.982C11.5 18.834 10.503 19.296 9.854 18.745L5.875 15.374L3.5 15.375C2.948 15.375 2.5 14.927 2.5 14.375V9.62497C2.5 9.07297 2.948 8.62497 3.5 8.62497L5.875 8.62498Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgVolumeDown);
export default Memo;