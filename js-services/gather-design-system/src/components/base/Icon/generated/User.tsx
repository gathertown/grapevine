import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgUser = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M5 20C5 17.544 6.991 15.553 9.447 15.553H14.553C17.009 15.553 19 17.544 19 20M15.0052 5.2448C16.6649 6.90453 16.6649 9.59548 15.0052 11.2552C13.3455 12.9149 10.6545 12.9149 8.99479 11.2552C7.33506 9.59548 7.33506 6.90453 8.99479 5.2448C10.6545 3.58507 13.3455 3.58507 15.0052 5.2448Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgUser);
export default Memo;