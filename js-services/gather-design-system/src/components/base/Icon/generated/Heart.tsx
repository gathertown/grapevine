import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgHeart = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M21 9.9375C21 15.8672 12.5208 20.25 11.75 20.25C10.9792 20.25 2.5 15.8672 2.5 9.9375C2.5 5.8125 5.06944 3.75 7.63889 3.75C10.2083 3.75 11.75 5.29688 11.75 5.29688C11.75 5.29688 13.2917 3.75 15.8611 3.75C18.4306 3.75 21 5.8125 21 9.9375Z" stroke="currentColor" strokeWidth={1.5} strokeLinejoin="round" /></svg>;
const Memo = memo(SvgHeart);
export default Memo;