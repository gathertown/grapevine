import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgVideoX = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M11 13.5L8 10.5M11 10.5L8 13.5M16 14.5L19.5297 16.3811C19.6821 16.4623 19.8529 16.5027 20.0255 16.4983C20.1981 16.4939 20.3666 16.4449 20.5146 16.356C20.6627 16.2672 20.7852 16.1415 20.8702 15.9913C20.9553 15.841 21 15.6713 21 15.4986V8.50136C21 8.3287 20.9553 8.15898 20.8702 8.00873C20.7852 7.85847 20.6627 7.7328 20.5146 7.64395C20.3666 7.55509 20.1981 7.50608 20.0255 7.50169C19.8529 7.49729 19.6821 7.53766 19.5297 7.61887L16 9.5M6 5.5H13C14.6569 5.5 16 6.84315 16 8.5V15.5C16 17.1569 14.6569 18.5 13 18.5H6C4.34315 18.5 3 17.1569 3 15.5V8.5C3 6.84315 4.34315 5.5 6 5.5Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgVideoX);
export default Memo;