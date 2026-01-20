import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgChatBubbleDashed = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M21.5 11.9999C21.5 6.99988 17.8056 3.99988 12 3.99988C6.19447 3.99988 2.50003 6.99988 2.50003 11.9999C2.50003 13.2942 3.39425 15.4895 3.53659 15.8308C3.5496 15.8619 3.56249 15.8904 3.57412 15.9221C3.67159 16.1879 4.06315 17.5821 2.50003 19.6438C4.61114 20.6438 6.85313 18.9999 6.85313 18.9999C8.40428 19.8153 10.2499 19.9999 12 19.9999C17.8056 19.9999 21.5 16.9999 21.5 11.9999Z" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" strokeDasharray="1.8 3.6" /></svg>;
const Memo = memo(SvgChatBubbleDashed);
export default Memo;