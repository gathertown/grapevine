import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgUserCard = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M15 9.5H19M17.4 13.5H15M12.095 16.5C11.92 16.061 11.65 15.667 11.303 15.346C10.716 14.802 9.946 14.5 9.146 14.5H7.854C7.054 14.5 6.284 14.802 5.697 15.346C5.35 15.667 5.08 16.061 4.905 16.5M10.091 8.15901C10.9697 9.03769 10.9697 10.4623 10.091 11.341C9.21233 12.2197 7.78771 12.2197 6.90903 11.341C6.03035 10.4623 6.03035 9.03769 6.90903 8.15901C7.78771 7.28033 9.21233 7.28033 10.091 8.15901ZM2 18.5V5.541C2 4.414 2.914 3.5 4.041 3.5H20C21.105 3.5 22 4.395 22 5.5V18.5C22 19.605 21.105 20.5 20 20.5H4C2.895 20.5 2 19.605 2 18.5Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgUserCard);
export default Memo;