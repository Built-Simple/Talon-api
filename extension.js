const vscode = require('vscode');
const https = require('https');

function activate(context) {
    console.log('Talon Error Prevention with Auto-Fix is active!');
    
    // Analyze command (just show errors)
    let analyzeCommand = vscode.commands.registerCommand('talon.analyzeFile', async function () {
        await analyzeFile(false);
    });
    
    // Fix command (apply fixes)
    let fixCommand = vscode.commands.registerCommand('talon.fixErrors', async function () {
        await analyzeFile(true);
    });
    
    context.subscriptions.push(analyzeCommand, fixCommand);
    
    // Status bar
    const statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBar.text = '$(tools) Talon Fix';
    statusBar.tooltip = 'Click to auto-fix Python errors';
    statusBar.command = 'talon.fixErrors';
    statusBar.show();
    context.subscriptions.push(statusBar);
    
    vscode.window.showInformationMessage('Talon Auto-Fix ready! Click status bar or use Command Palette');
}

async function analyzeFile(applyFixes) {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        vscode.window.showErrorMessage('No active editor!');
        return;
    }

    if (editor.document.languageId !== 'python') {
        vscode.window.showErrorMessage('Talon only works with Python files!');
        return;
    }

    const code = editor.document.getText();
    
    vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        title: applyFixes ? "Auto-fixing Python errors..." : "Analyzing Python code...",
        cancellable: false
    }, async (progress) => {
        try {
            const data = JSON.stringify({ 
                code: code,
                fix_errors: applyFixes 
            });
            
            const options = {
                hostname: 'talon-api-production.up.railway.app',
                port: 443,
                path: '/v1/analyze',
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Content-Length': data.length
                }
            };

            const result = await new Promise((resolve, reject) => {
                const req = https.request(options, (res) => {
                    let body = '';
                    res.on('data', (chunk) => body += chunk);
                    res.on('end', () => {
                        try {
                            resolve(JSON.parse(body));
                        } catch (e) {
                            reject(e);
                        }
                    });
                });
                
                req.on('error', reject);
                req.write(data);
                req.end();
            });

            if (result.errors && result.errors.length > 0) {
                if (applyFixes && result.fixed_code) {
                    // Apply the fixes
                    const edit = new vscode.WorkspaceEdit();
                    const fullRange = new vscode.Range(
                        editor.document.positionAt(0),
                        editor.document.positionAt(editor.document.getText().length)
                    );
                    edit.replace(editor.document.uri, fullRange, result.fixed_code);
                    
                    await vscode.workspace.applyEdit(edit);
                    
                    vscode.window.showInformationMessage(
                        `✨ Fixed ${result.fixes_applied} errors automatically!`,
                        'View Changes'
                    ).then(selection => {
                        if (selection === 'View Changes') {
                            vscode.commands.executeCommand('workbench.action.files.openFile');
                        }
                    });
                } else {
                    // Just show errors
                    const choice = await vscode.window.showWarningMessage(
                        `Found ${result.errors.length} errors. Would you like to auto-fix them?`,
                        'Auto-Fix All',
                        'Show Details'
                    );
                    
                    if (choice === 'Auto-Fix All') {
                        await analyzeFile(true);
                    } else if (choice === 'Show Details') {
                        let message = '';
                        result.errors.forEach((error, index) => {
                            message += `${index + 1}. Line ${error.line + 1}: ${error.type}\n`;
                            message += `   ${error.message}\n\n`;
                        });
                        
                        vscode.window.showInformationMessage(message, { modal: true });
                    }
                }
            } else {
                vscode.window.showInformationMessage('No errors found! Your code is perfect! 🎉');
            }

            // Update status bar
            if (result.usage) {
                statusBar.tooltip = `Auto-fix Python errors | Usage: ${result.usage}/100 this month`;
            }

        } catch (error) {
            vscode.window.showErrorMessage('Failed to analyze: ' + error.message);
        }
    });
}

function deactivate() {}

module.exports = {
    activate,
    deactivate
}