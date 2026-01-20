import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgArrowRightSemi = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M12 21.25C6.89137 21.25 2.75 17.1086 2.75 12C2.75 6.89137 6.89137 2.75 12 2.75M16.625 3.98749C17.4767 4.48018 18.2426 5.10477 18.8947 5.83333M16.625 20.0125C17.4767 19.5198 18.2426 18.8952 18.8947 18.1667M21.0751 10.2005C21.1898 10.7826 21.25 11.3843 21.25 12C21.25 12.6157 21.1898 13.2174 21.0751 13.7995M12.75 8.5L16.25 12L12.75 15.5M15.25 12H7.75" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgArrowRightSemi);
export default Memo;