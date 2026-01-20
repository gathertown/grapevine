import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgCreditCard = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path fillRule="evenodd" clipRule="evenodd" d="M3.5 7.75C3.5 6.50736 4.50736 5.5 5.75 5.5H17.75C18.9926 5.5 20 6.50736 20 7.75V9H3.5V7.75ZM2 9.75V7.75C2 5.67893 3.67893 4 5.75 4H17.75C19.8211 4 21.5 5.67893 21.5 7.75V9.75V16.75C21.5 18.8211 19.8211 20.5 17.75 20.5H5.75C3.67893 20.5 2 18.8211 2 16.75V9.75ZM20 10.5V16.75C20 17.9926 18.9926 19 17.75 19H5.75C4.50736 19 3.5 17.9926 3.5 16.75V10.5H20ZM6 15.75C6 15.3358 6.33579 15 6.75 15H8.75C9.16421 15 9.5 15.3358 9.5 15.75C9.5 16.1642 9.16421 16.5 8.75 16.5H6.75C6.33579 16.5 6 16.1642 6 15.75Z" fill="currentColor" /></svg>;
const Memo = memo(SvgCreditCard);
export default Memo;