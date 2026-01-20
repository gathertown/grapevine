import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgUserArrowLeft = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M17 20C17 17.544 15.009 15.553 12.553 15.553H7.447C4.991 15.553 3 17.544 3 20M22 12H17M17 12L19 14M17 12L19 9.99999M7.03024 5.41814C5.39004 7.05834 5.39004 9.71763 7.03024 11.3578C8.67044 12.998 11.3297 12.998 12.9699 11.3578C14.6101 9.71764 14.6101 7.05835 12.9699 5.41814C11.3297 3.77794 8.67045 3.77794 7.03024 5.41814Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgUserArrowLeft);
export default Memo;